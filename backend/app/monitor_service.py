"""Real stream monitoring service.

This module owns ffmpeg capture processes, Whisper transcription, keyword
matching, clip creation, and live status updates. Each station runs separately
so one broken stream does not stop the other monitor slots.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .language_profiles import LANGUAGE_PROFILES
from .matcher import KeywordMatcher
from .models import KeywordConfig, PipelineConfig, Station
from .settings import DEFAULT_OUTPUT_DIR, DEFAULT_TRANSCRIPT_DIR
from .store import add_alert, list_alerts


@dataclass
class MonitorSlot:
    station: Station
    work_dir: Path
    process: subprocess.Popen | None = None
    task: asyncio.Task | None = None
    status: str = "idle"
    error_message: str = ""
    last_transcript: str = ""
    last_transcript_at: datetime | None = None
    matched_keywords: list[str] = field(default_factory=list)
    chunk_history: deque[str] = field(default_factory=lambda: deque(["pending"] * 10, maxlen=10))
    ring_buffer: deque[Path] = field(default_factory=deque)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    alert_count: int = 0
    chunk_index: int = 0
    paused: bool = False


class MonitorService:
    def __init__(self) -> None:
        self.slots: dict[str, MonitorSlot] = {}  # keyed by station UUID
        self.keywords = KeywordConfig()
        self.pipeline = PipelineConfig()
        self.total_chunks = 0
        self.total_matches = 0
        self.total_clips = 0
        self.matcher = KeywordMatcher()
        self._model = None
        self._model_key: tuple[str, str, str] | None = None
        self._clients: set[asyncio.Queue] = set()

    def start(self, stations: list[Station], keywords: KeywordConfig, pipeline: PipelineConfig) -> None:
        self.keywords = keywords
        self.pipeline = pipeline
        self._ensure_directories()
        self.matcher.load_for_languages({station.languageCode for station in stations})
        for station in stations:
            if station.id in self.slots:
                continue
            slot = MonitorSlot(station=station, work_dir=self._station_work_dir(station))
            slot.ring_buffer = deque(maxlen=max(1, self.pipeline.preBufferSeconds // self.pipeline.chunkSeconds + 2))
            self.slots[station.id] = slot
            slot.task = asyncio.create_task(self._run_slot(slot))
        asyncio.create_task(self._broadcast(self.snapshot()))

    def remove(self, station_id: int) -> None:
        slot = self.slots.pop(station_id, None)
        if slot:
            self._stop_process(slot)
            if slot.task:
                slot.task.cancel()

    def pause(self, station_id: int) -> None:
        slot = self.slots.get(station_id)
        if slot:
            slot.paused = True
            slot.status = "paused"
            self._stop_process(slot)

    def resume(self, station_id: int) -> None:
        slot = self.slots.get(station_id)
        if slot and slot.paused:
            slot.paused = False
            slot.task = asyncio.create_task(self._run_slot(slot))

    def stop_all(self) -> None:
        for station_id in list(self.slots):
            self.remove(station_id)

    def patch_keywords(self, keywords: KeywordConfig) -> None:
        self.keywords = keywords

    def patch_pipeline(self, pipeline: PipelineConfig) -> None:
        self.pipeline = pipeline

    def snapshot(self) -> dict:
        alerts = list_alerts()
        return {
            "connected": True,
            "activeSlots": len(self.slots),
            "totalChunksProcessed": self.total_chunks,
            "totalMatchesSession": self.total_matches,
            "totalClipsSaved": self.total_clips,
            "diskFreeMB": self._disk_free_mb(),
            "loadedSpaCyModels": self.matcher.loaded_models(),
            "stationStatuses": [self._slot_status(slot) for slot in self.slots.values()],
            "unreviewedAlerts": len([alert for alert in alerts if not alert["reviewed"]]),
        }

    async def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._clients.add(queue)
        await queue.put(self.snapshot())
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._clients.discard(queue)

    async def _broadcast(self, payload: dict) -> None:
        # Every connected browser receives the same status snapshot after
        # meaningful monitor changes.
        for queue in list(self._clients):
            await queue.put(payload)

    async def _run_slot(self, slot: MonitorSlot) -> None:
        if shutil.which("ffmpeg") is None:
            slot.status = "error"
            slot.error_message = "ffmpeg is not installed or not on PATH."
            await self._broadcast(self.snapshot())
            return

        slot.work_dir.mkdir(parents=True, exist_ok=True)
        processed: set[Path] = set()
        streams = slot.station.streams
        if not streams:
            slot.status = "error"
            slot.error_message = "Station has no stream URL."
            await self._broadcast(self.snapshot())
            return

        for stream_index, stream in enumerate(streams, start=1):
            if slot.paused:
                return
            slot.status = "capturing"
            slot.error_message = ""
            self._start_ffmpeg(slot, stream.url, stream_index)
            await self._broadcast(self.snapshot())
            try:
                while slot.process and slot.process.poll() is None and not slot.paused:
                    await self._process_ready_chunks(slot, processed)
                    await asyncio.sleep(1)
                await self._process_ready_chunks(slot, processed, include_latest=True)
            finally:
                await self._stop_process_async(slot)
            if not slot.error_message and not slot.paused:
                slot.error_message = f"Stream ended on fallback {stream_index}."
        if not slot.paused:
            slot.status = "error"
            slot.error_message = slot.error_message or "All stream fallbacks failed."
            await self._broadcast(self.snapshot())

    def _start_ffmpeg(self, slot: MonitorSlot, url: str, stream_index: int) -> None:
        pattern = slot.work_dir / f"stream{stream_index}_%06d.wav"
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            url,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "segment",
            "-segment_time",
            str(self.pipeline.chunkSeconds),
            "-reset_timestamps",
            "1",
            str(pattern),
        ]
        # stderr=DEVNULL prevents the pipe buffer from filling up and blocking
        # ffmpeg when nobody is reading it (64KB limit on macOS/Linux).
        slot.process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    async def _process_ready_chunks(self, slot: MonitorSlot, processed: set[Path], include_latest: bool = False) -> None:
        chunks = sorted(slot.work_dir.glob("*.wav"))
        ready = chunks if include_latest else chunks[:-1]
        for chunk in ready:
            if chunk in processed or not chunk.exists():
                continue
            processed.add(chunk)
            slot.ring_buffer.append(chunk)
            slot.chunk_index += 1
            slot.status = "transcribing"
            await self._broadcast(self.snapshot())
            transcript = await asyncio.to_thread(self._transcribe, chunk, slot.station.languageCode)
            slot.last_transcript = transcript
            slot.last_transcript_at = datetime.now(timezone.utc)
            self.total_chunks += 1
            matches, mode_used, model_used = self.matcher.find_matches(transcript, slot.station.languageCode, self.keywords)
            slot.matched_keywords = matches
            slot.chunk_history.append("match" if matches else "none")
            if matches:
                slot.status = "match"
                for keyword in matches:
                    clip_path = self._make_clip(slot, keyword)
                    self._record_alert(slot, keyword, transcript, mode_used, model_used, clip_path)
            else:
                slot.status = "capturing"
            await self._broadcast(self.snapshot())

    def _transcribe(self, chunk: Path, language_code: str) -> str:
        if self._model is None or self._model_key != (self.pipeline.whisperModel, self.pipeline.device, self.pipeline.computeType):
            from faster_whisper import WhisperModel

            device = "cpu" if self.pipeline.device == "auto" else self.pipeline.device
            compute_type = "int8" if self.pipeline.computeType == "auto" and device == "cpu" else self.pipeline.computeType
            if compute_type == "auto":
                compute_type = "float16"
            self._model = WhisperModel(self.pipeline.whisperModel, device=device, compute_type=compute_type)
            self._model_key = (self.pipeline.whisperModel, self.pipeline.device, self.pipeline.computeType)

        language = None
        if self.pipeline.languageHintMode == "per-station":
            language = language_code
        elif self.pipeline.languageHintMode == "manual" and self.pipeline.manualLanguageCode:
            language = self.pipeline.manualLanguageCode

        segments, _info = self._model.transcribe(str(chunk), language=language)
        return " ".join(segment.text.strip() for segment in segments).strip()

    def _make_clip(self, slot: MonitorSlot, keyword: str) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        day_dir = Path(self.pipeline.outputDirectory) / stamp[:8]
        day_dir.mkdir(parents=True, exist_ok=True)
        safe_keyword = "".join(ch for ch in keyword.lower() if ch.isalnum() or ch in ("-", "_"))[:24] or "match"
        output = day_dir / f"{slot.station.slug or slot.station.id}_{slot.station.languageCode}_{stamp}_{safe_keyword}.wav"
        chunks = [path for path in slot.ring_buffer if path.exists()]
        if not chunks:
            return ""
        list_file = slot.work_dir / f"concat_{uuid.uuid4().hex}.txt"
        list_file.write_text("".join(f"file '{path.resolve()}'\n" for path in chunks), encoding="utf-8")
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(output.resolve())]
        result = subprocess.run(command, capture_output=True, text=True)
        list_file.unlink(missing_ok=True)
        return str(output) if result.returncode == 0 else ""

    def _record_alert(self, slot: MonitorSlot, keyword: str, transcript: str, mode_used: str, model_used: str | None, clip_path: str) -> None:
        slot.alert_count += 1
        self.total_matches += 1
        self.total_clips += 1 if clip_path else 0
        add_alert({
            "id": str(uuid.uuid4()),
            "stationId": slot.station.id,
            "stationName": slot.station.name,
            "countryName": slot.station.location.countryName,
            "countryCode": slot.station.location.countryCode,
            "languageCode": slot.station.languageCode,
            "matchedKeyword": keyword,
            "transcriptSnippet": transcript,
            "fullTranscriptPath": self._append_transcript(slot, transcript),
            "clipPath": clip_path,
            "clipDurationSeconds": len(slot.ring_buffer) * self.pipeline.chunkSeconds,
            "detectedAt": datetime.now(timezone.utc).isoformat(),
            "reviewed": False,
            "chunkIndex": slot.chunk_index,
            "matchMode": mode_used,
            "spaCyModelUsed": model_used,
        })

    def _append_transcript(self, slot: MonitorSlot, transcript: str) -> str:
        out_dir = Path(self.pipeline.transcriptLogDirectory)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{slot.station.slug or slot.station.id}_{slot.station.languageCode}_{datetime.now().strftime('%Y%m%d')}.txt"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{datetime.now().isoformat()}] {transcript}\n")
        return str(path)

    def _stop_process(self, slot: MonitorSlot) -> None:
        """Non-blocking terminate — safe to call from sync or async context."""
        if slot.process and slot.process.poll() is None:
            slot.process.terminate()
            # Do not wait here — waiting blocks the event loop. The OS cleans
            # up the child process when it exits after SIGTERM.
        slot.process = None

    async def _stop_process_async(self, slot: MonitorSlot) -> None:
        """Terminate ffmpeg and wait off-thread so the event loop stays free."""
        proc = slot.process
        slot.process = None
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                await asyncio.to_thread(proc.wait, 3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _slot_status(self, slot: MonitorSlot) -> dict:
        return {
            "stationId": slot.station.id,
            "languageCode": slot.station.languageCode,
            "status": slot.status,
            "errorMessage": slot.error_message,
            "lastTranscriptSnippet": slot.last_transcript or "Waiting for transcript.",
            "lastTranscriptAt": slot.last_transcript_at.isoformat() if slot.last_transcript_at else None,
            "matchedKeywordsInSnippet": slot.matched_keywords,
            "chunkHistory": list(slot.chunk_history),
            "uptimeSeconds": max(0, int((datetime.now(timezone.utc) - slot.started_at).total_seconds())),
            "alertCount": slot.alert_count,
        }

    def _station_work_dir(self, station: Station) -> Path:
        return Path(self.pipeline.outputDirectory) / "_chunks" / f"{station.id}_{station.languageCode}"

    def _ensure_directories(self) -> None:
        Path(self.pipeline.outputDirectory).mkdir(parents=True, exist_ok=True)
        Path(self.pipeline.transcriptLogDirectory).mkdir(parents=True, exist_ok=True)
        DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        DEFAULT_TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)

    def _disk_free_mb(self) -> int:
        usage = shutil.disk_usage(Path(self.pipeline.outputDirectory) if Path(self.pipeline.outputDirectory).exists() else DEFAULT_OUTPUT_DIR)
        return int(usage.free / 1024 / 1024)


monitor_service = MonitorService()
