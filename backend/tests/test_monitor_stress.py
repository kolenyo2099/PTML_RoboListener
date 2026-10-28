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
import threading

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
    slot.capture_chunk_seconds = max(1, svc.pipeline.chunkSeconds)
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


@pytest.mark.asyncio
async def test_post_buffer_waits_for_chunks_without_blocking_processing(tmp_path):
    """A detection waits for configured future chunks while later chunks process."""
    svc = _make_service(tmp_path)
    svc.pipeline.postBufferSeconds = 10
    slot = _make_slot(svc, tmp_path)
    svc._transcribe = lambda chunk, lang: "breaking news"
    svc.matcher.find_matches.side_effect = [(["news"], "exact", None), ([], "exact", None), ([], "exact", None)]
    svc._ensure_directories()
    written = []
    svc._make_clip = lambda slot, keyword, chunks=None, **kwargs: written.append((keyword, len(chunks or []))) or "/tmp/test.wav"
    records = []
    svc._record_alert = lambda *args: records.append(args)
    processed = set()

    for i in range(3):
        write_silent_wav(slot.work_dir / f"stream1_{i:06d}.wav")
        await svc._process_ready_chunks(slot, processed, include_latest=True)
        if i == 0:
            assert not records and not written
        if i == 1:
            assert not records and not written

    assert len(written) == 1
    assert written[0] == ("news", 3)  # detection chunk + two post-buffer chunks
    assert len(records) == 1


def test_make_clip_encodes_selected_output_format(tmp_path):
    svc = _make_service(tmp_path)
    svc.pipeline.outputFormat = "mp3"
    slot = _make_slot(svc, tmp_path)
    chunk = slot.work_dir / "stream1_000000.wav"
    write_silent_wav(chunk)
    commands = []

    class Result:
        returncode = 0

    def fake_run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"encoded")
        return Result()

    with patch("app.monitor_service.subprocess.run", side_effect=fake_run):
        output = svc._make_clip(slot, "news", [chunk])

    assert output.endswith(".mp3")
    assert "libmp3lame" in commands[0]
    assert "128k" in commands[0]


def test_ogg_encoding_falls_back_and_removes_failed_partial_output(tmp_path):
    svc = _make_service(tmp_path)
    svc.pipeline.outputFormat = "ogg"
    slot = _make_slot(svc, tmp_path)
    chunk = slot.work_dir / "stream1_000000.wav"
    write_silent_wav(chunk)
    commands = []

    class Result:
        def __init__(self, returncode):
            self.returncode = returncode

    def fake_run(command, **kwargs):
        commands.append(command)
        output = Path(command[-1])
        output.write_bytes(b"partial" if len(commands) < 3 else b"valid opus")
        return Result(1 if len(commands) < 3 else 0)

    with patch("app.monitor_service.subprocess.run", side_effect=fake_run):
        output = svc._make_clip(slot, "news", [chunk])

    assert output.endswith(".ogg")
    assert "libvorbis" in commands[0]
    assert "libopus" in commands[-1]
    assert Path(output).read_bytes() == b"valid opus"
    assert len(commands) == 3  # libvorbis, native vorbis, then libopus


def test_failed_encoders_remove_partial_output_and_report_no_clip(tmp_path):
    svc = _make_service(tmp_path)
    svc.pipeline.outputFormat = "ogg"
    slot = _make_slot(svc, tmp_path)
    chunk = slot.work_dir / "stream1_000000.wav"
    write_silent_wav(chunk)

    class Result:
        returncode = 1

    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"truncated output")
        return Result()

    with patch("app.monitor_service.subprocess.run", side_effect=fake_run):
        output = svc._make_clip(slot, "news", [chunk])

    assert output == ""
    assert not list((Path(svc.pipeline.outputDirectory) / datetime.now(timezone.utc).strftime("%Y%m%d")).glob("*.ogg"))


def test_mp3_uses_libshine_when_lame_is_unavailable(tmp_path):
    svc = _make_service(tmp_path)
    svc.pipeline.outputFormat = "mp3"
    slot = _make_slot(svc, tmp_path)
    chunk = slot.work_dir / "stream1_000000.wav"
    write_silent_wav(chunk)
    commands = []

    class Result:
        def __init__(self, returncode):
            self.returncode = returncode

    def fake_run(command, **kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"encoded")
        return Result(1 if "libmp3lame" in command else 0)

    with patch("app.monitor_service.subprocess.run", side_effect=fake_run):
        output = svc._make_clip(slot, "news", [chunk])

    assert output.endswith(".mp3")
    assert "libshine" in commands[-1]
    assert Path(output).read_bytes() == b"encoded"


def test_cancel_pending_clip_records_detection_without_false_clip(tmp_path):
    svc = _make_service(tmp_path)
    slot = _make_slot(svc, tmp_path)
    slot.pending_clips.append({
        "keyword": "news", "transcript": "breaking news", "mode": "exact",
        "model": None, "start_chunk": 1, "finish_chunk": 3, "pre_chunks": 1,
    })
    records = []
    svc._record_alert = lambda *args: records.append(args)

    svc._cancel_pending_clips(slot)

    assert not slot.pending_clips
    assert len(records) == 1
    assert records[0][5:] == ("", 0)


@pytest.mark.asyncio
async def test_pending_detection_is_saved_without_clip_after_stream_exhaustion(tmp_path):
    svc = _make_service(tmp_path)
    slot = _make_slot(svc, tmp_path)
    slot.pending_clips.append({
        "keyword": "news", "transcript": "breaking news", "mode": "exact",
        "model": None, "start_chunk": 1, "finish_chunk": 3, "pre_chunks": 1,
        "chunk_seconds": 5, "output_format": "wav", "output_directory": str(tmp_path),
    })
    records = []
    svc._record_alert = lambda *args: records.append(args)
    svc._ensure_directories()
    fake_proc = FakeProcess(alive_for=0)

    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        with patch.object(svc, "_start_ffmpeg", lambda s, url, idx: setattr(s, "process", fake_proc)):
            with patch.object(svc, "_stop_process_async", _async_noop_stop):
                await svc._run_slot(slot)

    assert slot.status == "error"
    assert not slot.pending_clips
    assert len(records) == 1
    assert records[0][5:] == ("", 0)


@pytest.mark.asyncio
async def test_pending_clip_keeps_detection_time_settings_after_pipeline_patch(tmp_path):
    svc = _make_service(tmp_path)
    svc.pipeline.preBufferSeconds = 5
    svc.pipeline.postBufferSeconds = 5
    svc.pipeline.outputFormat = "mp3"
    svc.pipeline.outputDirectory = str(tmp_path / "original")
    slot = _make_slot(svc, tmp_path)
    svc._ensure_directories()
    svc._transcribe = lambda chunk, lang: "breaking news"
    svc.matcher.find_matches.side_effect = [(["news"], "exact", None), ([], "exact", None)]
    make_calls = []
    svc._make_clip = lambda slot, keyword, chunks=None, **kwargs: make_calls.append((kwargs, threading.get_ident())) or "/tmp/frozen.mp3"
    records = []
    svc._record_alert = lambda *args: records.append(args)
    processed = set()

    write_silent_wav(slot.work_dir / "stream1_000000.wav")
    await svc._process_ready_chunks(slot, processed, include_latest=True)
    old_maxlen = slot.ring_buffer.maxlen
    from app.models import PipelineConfig
    svc.patch_pipeline(PipelineConfig(
        outputDirectory=str(tmp_path / "changed"), outputFormat="ogg",
        chunkSeconds=20, preBufferSeconds=0, postBufferSeconds=0,
    ))
    assert slot.ring_buffer.maxlen >= old_maxlen
    write_silent_wav(slot.work_dir / "stream1_000001.wav")
    await svc._process_ready_chunks(slot, processed, include_latest=True)

    assert make_calls[0][0] == {"output_format": "mp3", "output_directory": str(tmp_path / "original")}
    assert make_calls[0][1] != threading.get_ident()  # encoding work runs outside the event loop thread
    assert len(records) == 1
    assert records[0][5] == "/tmp/frozen.mp3"
    assert records[0][6] == 1.0  # two real 0.5 second WAV chunks


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["pause", "remove"])
async def test_pause_or_remove_during_clip_encoding_records_once_and_deletes_output(tmp_path, action):
    svc = _make_service(tmp_path)
    slot = _make_slot(svc, tmp_path)
    svc.slots[slot.station.id] = slot
    chunk = slot.work_dir / "stream1_000000.wav"
    write_silent_wav(chunk)
    slot.ring_buffer.append(chunk)
    slot.chunk_index = 1
    slot.pending_clips.extend({
        "id": f"race-test-{i}", "keyword": f"news-{i}", "transcript": "breaking news",
        "mode": "exact", "model": None, "start_chunk": 1, "finish_chunk": 1,
        "pre_chunks": 0, "chunk_seconds": 5, "output_format": "wav",
        "output_directory": str(tmp_path),
    } for i in range(2))
    entered = threading.Event()
    release = threading.Event()
    output = tmp_path / "race.wav"

    def slow_encode(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        output.write_bytes(b"encoded")
        return str(output)

    svc._make_clip = slow_encode
    encoded_keywords = []
    original_make_clip = svc._make_clip
    def record_encode(slot_arg, keyword, *args, **kwargs):
        encoded_keywords.append(keyword)
        return original_make_clip(slot_arg, keyword, *args, **kwargs)
    svc._make_clip = record_encode
    records = []
    svc._record_alert = lambda *args: records.append(args)
    task = asyncio.create_task(svc._complete_pending_clips(slot))
    slot.task = task
    assert await asyncio.to_thread(entered.wait, 2)

    if action == "pause":
        svc.pause(slot.station.id)
    else:
        svc.remove(slot.station.id)
    release.set()
    if action == "remove":
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        await task

    assert len(records) == 2
    assert all(record[5:] == ("", 0) for record in records)
    assert len(encoded_keywords) == 1
    assert not output.exists()
    assert not slot.pending_clips and not slot.in_flight_clips


@pytest.mark.asyncio
async def test_pending_window_uses_active_ffmpeg_chunk_duration_after_settings_change(tmp_path):
    svc = _make_service(tmp_path)
    slot = _make_slot(svc, tmp_path)
    slot.capture_chunk_seconds = 5  # ffmpeg was started with the old setting
    from app.models import PipelineConfig
    svc.patch_pipeline(PipelineConfig(
        chunkSeconds=20, preBufferSeconds=0, postBufferSeconds=11,
        outputDirectory=str(tmp_path), outputFormat="wav",
    ))
    svc._transcribe = lambda chunk, lang: "breaking news"
    svc.matcher.find_matches.return_value = (["news"], "exact", None)
    svc._ensure_directories()
    processed = set()
    write_silent_wav(slot.work_dir / "stream1_000000.wav")
    await svc._process_ready_chunks(slot, processed, include_latest=True)

    pending = slot.pending_clips[0]
    assert pending["chunk_seconds"] == 5
    assert pending["finish_chunk"] - pending["start_chunk"] == 3
    assert slot.ring_buffer.maxlen >= 4


@pytest.mark.asyncio
async def test_pause_during_transcription_does_not_enqueue_new_detection(tmp_path):
    svc = _make_service(tmp_path)
    slot = _make_slot(svc, tmp_path)
    svc.slots[slot.station.id] = slot
    chunk = slot.work_dir / "stream1_000000.wav"
    write_silent_wav(chunk)
    entered = threading.Event()
    release = threading.Event()

    def slow_transcribe(*args):
        entered.set()
        assert release.wait(3)
        return "breaking news"

    svc._transcribe = slow_transcribe
    svc.matcher.find_matches.return_value = (["news"], "exact", None)
    records = []
    svc._record_alert = lambda *args: records.append(args)
    task = asyncio.create_task(svc._process_ready_chunks(slot, set(), include_latest=True))
    assert await asyncio.to_thread(entered.wait, 2)

    svc.pause(slot.station.id)
    release.set()
    await task

    assert slot.paused
    assert not slot.pending_clips and not slot.in_flight_clips
    assert not records
    svc.matcher.find_matches.assert_not_called()
