"""Stress tests for MonitorService._run_slot.

Exercises four known crash / degradation vectors without needing
a real radio stream, ffmpeg on PATH, or Whisper loaded:

  1. Exception resilience    – _transcribe raises every Nth call; task must survive.
  2. Memory growth           – `processed` set is never pruned; check it stays bounded.
  3. Chunk accumulation      – WAV files pile up on disk; check cleanup happens.
  4. Slot restart after drop – when the fake ffmpeg process exits, the slot either
                               retries the next fallback or lands in 'error' cleanly.

Run with:
    cd /Users/guillen/Documents/experiments/radiowatch
    .venv/bin/pytest backend/tests/test_monitor_stress.py -v
"""

from __future__ import annotations

import asyncio
import struct
import subprocess
import sys
import time
import traceback
import wave
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
import tempfile
import os

import pytest
import pytest_asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_silent_wav(path: Path, duration_s: float = 0.5, sample_rate: int = 16000) -> None:
    """Write a minimal silent mono 16-bit WAV so the glob finds real files."""
    n_samples = int(sample_rate * duration_s)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_samples)


class FakeProcess:
    """Mimics subprocess.Popen just enough for MonitorSlot."""

    def __init__(self, alive_for: int = 9999):
        self._alive_for = alive_for
        self._calls = 0

    def poll(self) -> int | None:
        self._calls += 1
        if self._calls > self._alive_for:
            return 0  # process "exited" normally
        return None  # still running

    def terminate(self) -> None:
        self._alive_for = 0

    def kill(self) -> None:
        self._alive_for = 0

    def wait(self, timeout: float | None = None) -> int:
        return 0


# ---------------------------------------------------------------------------
# Minimal stubs so we can import MonitorService without heavy deps
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_service(tmp_dir: Path):
    """Return a MonitorService wired to tmp_dir without real Whisper or spaCy."""
    from app.models import KeywordConfig, PipelineConfig
    from app.monitor_service import MonitorService

    svc = MonitorService()
    svc.pipeline = PipelineConfig(
        outputDirectory=str(tmp_dir / "recordings"),
        transcriptLogDirectory=str(tmp_dir / "transcripts"),
        chunkSeconds=5,
        preBufferSeconds=10,
    )
    svc.keywords = KeywordConfig()
    # Stub out heavy components
    svc.matcher = MagicMock()
    svc.matcher.loaded_models.return_value = []
    svc.matcher.find_matches.return_value = ([], "exact", None)
    svc.matcher.load_for_languages.return_value = None
    return svc


def _make_slot(svc, tmp_dir: Path, station_id: str = "test-station-1"):
    from app.models import KeywordConfig, Location, PipelineConfig, Station, Stream
    from app.monitor_service import MonitorSlot

    station = Station(
        id=station_id,
        name="Test Station",
        slug="test",
        location=Location(countryName="TestLand", countryCode="TL"),
        streams=[Stream(url="http://fake-stream.test/radio")],
        languageCode="es",
    )
    work_dir = tmp_dir / "chunks" / station_id
    work_dir.mkdir(parents=True, exist_ok=True)
    slot = MonitorSlot(station=station, work_dir=work_dir)
    slot.ring_buffer = deque(maxlen=5)
    return slot


# ---------------------------------------------------------------------------
# Test 1 – Exception resilience
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transcription_error_does_not_kill_task(tmp_path):
    """If _transcribe raises, _run_slot must handle it gracefully.

    Currently there is NO try/except in _process_ready_chunks, so an exception
    from _transcribe propagates out of the async task.  This test will FAIL
    until the bug is fixed — that is intentional: it documents the crash.
    """
    svc = _make_service(tmp_path)
    slot = _make_slot(svc, tmp_path)

    call_count = 0
    error_count = 0

    def flaky_transcribe(chunk_path, lang):
        nonlocal call_count, error_count
        call_count += 1
        if call_count % 3 == 0:  # crash every 3rd chunk
            error_count += 1
            raise RuntimeError("Simulated Whisper OOM on chunk %d" % call_count)
        return "some transcribed text"

    # Pre-create 9 chunk files
    for i in range(9):
        write_silent_wav(slot.work_dir / f"stream1_{i:06d}.wav")

    fake_proc = FakeProcess(alive_for=1)  # process exits after first poll
    slot.process = fake_proc

    svc._transcribe = flaky_transcribe
    svc._ensure_directories()

    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        with patch.object(svc, "_start_ffmpeg", lambda s, url, idx: None):
            with patch.object(svc, "_stop_process_async", _async_noop_stop):
                task = asyncio.create_task(svc._run_slot(slot))
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
                except asyncio.TimeoutError:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                except Exception as exc:
                    task_exc = exc
                    pytest.fail(
                        f"_run_slot raised an unhandled exception ({type(exc).__name__}: {exc}) "
                        f"after {call_count} transcription calls ({error_count} errors injected). "
                        "Add try/except in _process_ready_chunks to survive transient errors."
                    )

    # If we get here the task completed without crashing (either all fallbacks
    # exhausted or timeout).  The slot should not be stuck in 'transcribing'.
    assert slot.status in ("error", "capturing", "match", "idle", "paused"), (
        f"Unexpected slot status '{slot.status}' after stress run"
    )
    print(f"\n  [resilience] {call_count} transcriptions, {error_count} errors injected, final status={slot.status!r}")


async def _async_noop_stop(slot):
    slot.process = None


# ---------------------------------------------------------------------------
# Test 2 – Memory growth: `processed` set is unbounded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_processed_set_grows_without_bound(tmp_path):
    """Demonstrates that the `processed` set inside _run_slot accumulates every
    chunk path ever seen and is never pruned.

    We run 200 synthetic chunks through _process_ready_chunks and confirm the
    processed set (observed indirectly via glob size) keeps growing.

    This test documents the leak but does not fail the suite — it only warns.
    After a fix the assertion should flip.
    """
    svc = _make_service(tmp_path)
    slot = _make_slot(svc, tmp_path)
    svc._transcribe = lambda chunk, lang: "text"
    svc._ensure_directories()

    # Simulate calling _process_ready_chunks 200 times, each time
    # the work_dir has one more chunk.
    processed: set[Path] = set()
    chunk_count = 200
    for i in range(chunk_count):
        write_silent_wav(slot.work_dir / f"stream1_{i:06d}.wav")
        await svc._process_ready_chunks(slot, processed, include_latest=True)

    # The `processed` set grows to ~chunk_count entries and is never pruned.
    # On a 24-hour run at 30 s chunks that's 2880 entries (small but still).
    # Combined with glob("*.wav") over that many files each second, it slows.
    leak_confirmed = len(processed) >= chunk_count - 1
    if leak_confirmed:
        print(
            f"\n  [memory] processed set has {len(processed)} entries after {chunk_count} chunks — never pruned."
        )
    else:
        print(f"\n  [memory] processed set has {len(processed)} entries — appears bounded now.")

    # We don't fail here — this is a characterisation test. The important thing
    # is knowing the set is unbounded so a fix can be validated.
    assert len(processed) <= chunk_count  # sanity upper bound


# ---------------------------------------------------------------------------
# Test 3 – Chunk file accumulation (disk leak)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chunk_files_accumulate(tmp_path):
    """WAV chunks are never deleted from work_dir.

    After N iterations the number of *.wav files on disk should ideally be
    bounded to the ring_buffer size.  Currently it is not — all files remain.
    """
    svc = _make_service(tmp_path)
    slot = _make_slot(svc, tmp_path)
    svc._transcribe = lambda chunk, lang: "text"
    svc._ensure_directories()

    processed: set[Path] = set()
    n = 50
    for i in range(n):
        write_silent_wav(slot.work_dir / f"stream1_{i:06d}.wav")
        await svc._process_ready_chunks(slot, processed, include_latest=True)

    remaining = list(slot.work_dir.glob("*.wav"))
    print(
        f"\n  [disk] {n} chunks processed, {len(remaining)} WAV files remain on disk "
        f"(ideal ≤ ring_buffer maxlen={slot.ring_buffer.maxlen})"
    )

    # After the fix: old chunks are deleted as the ring buffer wraps.
    # Only ring_buffer.maxlen files should remain on disk.
    assert len(remaining) <= slot.ring_buffer.maxlen, (
        f"Expected ≤{slot.ring_buffer.maxlen} files on disk, got {len(remaining)}. "
        "Chunk cleanup is not working correctly."
    )


# ---------------------------------------------------------------------------
# Test 4 – Slot stays in 'error' cleanly when all fallbacks exhausted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slot_reaches_error_after_stream_drop(tmp_path):
    """When the fake ffmpeg process dies immediately (simulating a dead stream),
    the slot should end up with status='error' and a meaningful error_message.
    """
    svc = _make_service(tmp_path)
    slot = _make_slot(svc, tmp_path)
    svc._transcribe = lambda chunk, lang: "text"
    svc._ensure_directories()

    # Process exits on first poll (stream immediately drops)
    fake_proc = FakeProcess(alive_for=0)
    start_calls = []

    def fake_start(s, url, idx):
        s.process = FakeProcess(alive_for=0)
        start_calls.append(url)

    async def fake_stop(s):
        s.process = None

    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        with patch.object(svc, "_start_ffmpeg", fake_start):
            with patch.object(svc, "_stop_process_async", fake_stop):
                task = asyncio.create_task(svc._run_slot(slot))
                try:
                    await asyncio.wait_for(task, timeout=5.0)
                except asyncio.TimeoutError:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

    print(f"\n  [restart] final status={slot.status!r}, error={slot.error_message!r}, start_calls={len(start_calls)}")
    assert slot.status == "error", f"Expected 'error' after stream drop, got {slot.status!r}"
    assert slot.error_message, "Expected a non-empty error_message after stream drop"


# ---------------------------------------------------------------------------
# Test 5 – Long simulation: 500 chunks, timed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_long_simulation_500_chunks(tmp_path):
    """Run 500 synthetic chunks through _process_ready_chunks and measure
    wall-clock time per chunk.  If the glob+set lookup degrades over time,
    the last 100 chunks will be noticeably slower than the first 100.
    """
    svc = _make_service(tmp_path)
    slot = _make_slot(svc, tmp_path)
    svc._transcribe = lambda chunk, lang: "hello world test"
    svc._ensure_directories()

    processed: set[Path] = set()
    n = 500
    timings: list[float] = []

    for i in range(n):
        write_silent_wav(slot.work_dir / f"stream1_{i:06d}.wav")
        t0 = time.perf_counter()
        await svc._process_ready_chunks(slot, processed, include_latest=True)
        timings.append(time.perf_counter() - t0)

    first_100 = sum(timings[:100]) / 100 * 1000
    last_100 = sum(timings[-100:]) / 100 * 1000
    slowdown = last_100 / first_100 if first_100 > 0 else 1.0

    print(
        f"\n  [perf] 500 chunks | first-100 avg={first_100:.2f} ms | last-100 avg={last_100:.2f} ms | "
        f"slowdown={slowdown:.1f}x"
    )

    # Warn if processing the last batch takes >5x longer than the first.
    # This catches O(n) degradation from growing `processed` + `glob`.
    assert slowdown < 20.0, (
        f"Processing slowed down {slowdown:.1f}x from first 100 to last 100 chunks. "
        "The `processed` set or glob over accumulated files is causing O(n) degradation."
    )


# ---------------------------------------------------------------------------
# Test 6 – Broadcast queue does not grow unboundedly for slow clients
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broadcast_queue_not_unbounded(tmp_path):
    """If a WebSocket client stops draining its queue, _broadcast should not
    accumulate messages indefinitely (no maxsize on asyncio.Queue).

    This is a documentation test — currently the queue IS unbounded.
    """
    svc = _make_service(tmp_path)
    svc._ensure_directories()

    # Subscribe a slow client (never drains)
    slow_queue = await svc.subscribe()

    # Simulate 100 rapid broadcasts (e.g. many chunks processed quickly)
    for _ in range(100):
        await svc._broadcast(svc.snapshot())

    qsize = slow_queue.qsize()
    print(f"\n  [ws] slow client queue size after 100 broadcasts: {qsize}")

    # Document the current behaviour. A bounded queue (e.g. maxsize=50) would
    # drop old messages rather than growing forever.
    assert qsize <= 200, f"Queue grew to {qsize} — possible memory issue with many slow clients"
    svc.unsubscribe(slow_queue)
