"""Real stream monitoring service.

This module owns ffmpeg capture processes, Whisper transcription, keyword
matching, clip creation, and live status updates. Each station runs separately
so one broken stream does not stop the other monitor slots.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import uuid
import wave
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
    pending_clips: list[dict] = field(default_factory=list)
    in_flight_clips: dict[str, dict] = field(default_factory=dict)
    capture_chunk_seconds: int = 30


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
            slot.ring_buffer = deque(maxlen=self._clip_buffer_chunks())
            self.slots[station.id] = slot
            slot.task = asyncio.create_task(self._run_slot(slot))
        asyncio.create_task(self._broadcast(self.snapshot()))

    def remove(self, station_id: int) -> None:
        slot = self.slots.pop(station_id, None)
        if slot:
            self._cancel_pending_clips(slot)
            self._stop_process(slot)
            if slot.task:
                slot.task.cancel()

    def pause(self, station_id: int) -> None:
        slot = self.slots.get(station_id)
        if slot:
            self._cancel_pending_clips(slot)
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
        # Never shrink a live slot's buffer: a pending clip may rely on its
        # original window while settings are being edited.
        for slot in self.slots.values():
            slot.ring_buffer = deque(
                slot.ring_buffer,
                maxlen=max(slot.ring_buffer.maxlen or 0, self._clip_buffer_chunks(slot.capture_chunk_seconds)),
            )

    def _clip_buffer_chunks(self, capture_chunk_seconds: int | None = None) -> int:
        chunk_seconds = max(1, capture_chunk_seconds or self.pipeline.chunkSeconds)
        pre = max(0, self.pipeline.preBufferSeconds)
        post = max(0, self.pipeline.postBufferSeconds)
        return max(1, (pre + chunk_seconds - 1) // chunk_seconds + (post + chunk_seconds - 1) // chunk_seconds + 1)

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
            "ffmpegAvailable": shutil.which("ffmpeg") is not None,
            "ytDlpAvailable": shutil.which("yt-dlp") is not None,
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
            self._cancel_pending_clips(slot)
            await self._broadcast(self.snapshot())
            return

        slot.work_dir.mkdir(parents=True, exist_ok=True)
        processed: set[Path] = set()
        streams = slot.station.streams
        if not streams:
            slot.status = "error"
            slot.error_message = "Station has no stream URL."
            self._cancel_pending_clips(slot)
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
            self._cancel_pending_clips(slot)
            slot.status = "error"
            slot.error_message = slot.error_message or "All stream fallbacks failed."
            await self._broadcast(self.snapshot())

    # Platform URLs that ffmpeg cannot open directly — yt-dlp extracts the real
    # stream URL first. Time-limited URLs (e.g. YouTube) are valid for several
    # hours, which is long enough for a monitoring session.
    _PLATFORM_HOSTS = (
        "youtube.com", "youtu.be", "twitch.tv", "facebook.com",
        "instagram.com", "twitter.com", "x.com", "dailymotion.com",
        "vimeo.com", "tiktok.com", "kick.com",
    )

    def _resolve_url(self, url: str) -> str:
        """Return the direct stream URL. Uses yt-dlp for platform URLs."""
        url_lower = url.lower()
        is_platform = any(host in url_lower for host in self._PLATFORM_HOSTS)
        if not is_platform:
            return url
        if shutil.which("yt-dlp") is None:
            return url
        try:
            result = subprocess.run(
                ["yt-dlp", "-g", "--format", "bestaudio/best", "--no-playlist", url],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                resolved = result.stdout.strip().split("\n")[0]
                if resolved:
                    return resolved
        except Exception:
            pass
        return url

    def _start_ffmpeg(self, slot: MonitorSlot, url: str, stream_index: int) -> None:
        # This remains the true segment size for the lifetime of this process,
        # even if the user edits pipeline settings while capture is active.
        slot.capture_chunk_seconds = max(1, self.pipeline.chunkSeconds)
        resolved = self._resolve_url(url)
        pattern = slot.work_dir / f"stream{stream_index}_%06d.wav"
        is_http = resolved.lower().startswith(("http://", "https://"))
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
        if is_http:
            # Reconnect on dropped HTTP streams; user-agent avoids blocks from
            # servers that reject the default ffmpeg agent string.
            command += [
                "-reconnect", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "5",
                "-user_agent", "Mozilla/5.0 (compatible; RadioWatch/1.0)",
            ]
        command += [
            "-i", resolved,
            "-vn", "-ac", "1", "-ar", "16000",
            "-f", "segment",
            "-segment_time", str(self.pipeline.chunkSeconds),
            "-reset_timestamps", "1",
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

            # Evict the oldest chunk from disk when the ring buffer wraps so
            # WAV files don't accumulate indefinitely (disk + O(n) glob leak).
            evicted: Path | None = None
            if len(slot.ring_buffer) == slot.ring_buffer.maxlen:
                evicted = slot.ring_buffer[0]
            slot.ring_buffer.append(chunk)
            if evicted is not None:
                evicted.unlink(missing_ok=True)
                processed.discard(evicted)

            slot.chunk_index += 1
            await self._complete_pending_clips(slot)
            slot.status = "transcribing"
            await self._broadcast(self.snapshot())
            try:
                transcript = await asyncio.to_thread(self._transcribe, chunk, slot.station.languageCode)
            except Exception as exc:
                # A transient transcription failure (OOM, corrupt WAV, model
                # reload race) must not kill the monitoring task.  Log to the
                # slot history and continue with the next chunk.
                slot.chunk_history.append("error")
                slot.status = "capturing"
                slot.error_message = f"Transcription error on chunk {slot.chunk_index}: {exc}"
                await self._broadcast(self.snapshot())
                continue
            if slot.paused:
                # Pause may have arrived while transcription was running. The
                # user has already cancelled pending work, so don't enqueue a
                # fresh detection from this late result.
                slot.status = "paused"
                continue
            slot.error_message = ""
            slot.last_transcript = transcript
            slot.last_transcript_at = datetime.now(timezone.utc)
            self.total_chunks += 1
            matches, mode_used, model_used = self.matcher.find_matches(transcript, slot.station.languageCode, self.keywords)
            slot.matched_keywords = matches
            slot.chunk_history.append("match" if matches else "none")
            if matches:
                slot.status = "match"
                for keyword in matches:
                    capture_seconds = max(1, slot.capture_chunk_seconds)
                    post_chunks = (max(0, self.pipeline.postBufferSeconds) + capture_seconds - 1) // capture_seconds
                    slot.pending_clips.append({
                        "id": uuid.uuid4().hex,
                        "keyword": keyword, "transcript": transcript,
                        "mode": mode_used, "model": model_used,
                        "start_chunk": slot.chunk_index,
                        "finish_chunk": slot.chunk_index + post_chunks,
                        "pre_chunks": (max(0, self.pipeline.preBufferSeconds) + capture_seconds - 1) // capture_seconds,
                        "chunk_seconds": capture_seconds,
                        "output_format": self.pipeline.outputFormat,
                        "output_directory": self.pipeline.outputDirectory,
                    })
                await self._complete_pending_clips(slot)
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

    def _make_clip(self, slot: MonitorSlot, keyword: str, chunks: list[Path] | None = None, *, output_format: str | None = None, output_directory: str | None = None) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        day_dir = Path(output_directory or self.pipeline.outputDirectory) / stamp[:8]
        day_dir.mkdir(parents=True, exist_ok=True)
        safe_keyword = "".join(ch for ch in keyword.lower() if ch.isalnum() or ch in ("-", "_"))[:24] or "match"
        fmt = output_format or self.pipeline.outputFormat
        fmt = fmt if fmt in {"wav", "mp3", "ogg"} else "wav"
        output = day_dir / f"{slot.station.slug or slot.station.id}_{slot.station.languageCode}_{stamp}_{safe_keyword}_{uuid.uuid4().hex[:10]}.{fmt}"
        chunks = [path for path in (chunks if chunks is not None else list(slot.ring_buffer)) if path.exists()]
        if not chunks:
            return ""
        list_file = slot.work_dir / f"concat_{uuid.uuid4().hex}.txt"
        list_file.write_text("".join(f"file '{path.resolve()}'\n" for path in chunks), encoding="utf-8")
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file)]
        if fmt == "wav":
            encoder_options = [["-c:a", "pcm_s16le"]]
        elif fmt == "mp3":
            # libshine is commonly built into smaller FFmpeg distributions
            # that omit the higher quality libmp3lame encoder.
            encoder_options = [
                ["-c:a", "libmp3lame", "-b:a", "128k"],
                ["-c:a", "libshine", "-b:a", "128k"],
            ]
        else:
            # Ogg can carry Vorbis or Opus. Try the common Vorbis encoders,
            # then Opus for builds with neither Vorbis implementation.
            encoder_options = [
                ["-c:a", "libvorbis", "-q:a", "4"],
                ["-c:a", "vorbis", "-strict", "experimental", "-q:a", "4"],
                ["-c:a", "libopus", "-b:a", "96k"],
            ]
        output_arg = str(output.resolve())
        try:
            for options in encoder_options:
                output.unlink(missing_ok=True)
                result = subprocess.run(command + options + [output_arg], capture_output=True, text=True)
                if result.returncode == 0 and output.is_file() and output.stat().st_size > 0:
                    return str(output)
            output.unlink(missing_ok=True)
            return ""
        except Exception:
            output.unlink(missing_ok=True)
            raise
        finally:
            list_file.unlink(missing_ok=True)

    async def _complete_pending_clips(self, slot: MonitorSlot) -> None:
        ready = [item for item in slot.pending_clips if slot.chunk_index >= item["finish_chunk"]]
        waiting = [item for item in slot.pending_clips if slot.chunk_index < item["finish_chunk"]]
        # Keep ready-but-not-yet-encoding items cancellable while another clip
        # is in flight; otherwise a stop could drop the rest of this batch.
        slot.pending_clips = ready + waiting
        for pending in ready:
            if pending not in slot.pending_clips:
                # A pause/remove may have cancelled this item while an earlier
                # clip in this same ready batch was being encoded.
                continue
            slot.pending_clips = [item for item in slot.pending_clips if item["id"] != pending["id"]]
            chunks = list(slot.ring_buffer)[-(pending["pre_chunks"] + (pending["finish_chunk"] - pending["start_chunk"]) + 1):]
            clip_id = pending["id"]
            slot.in_flight_clips[clip_id] = pending
            worker = asyncio.create_task(asyncio.to_thread(
                self._make_clip, slot, pending["keyword"], chunks,
                output_format=pending["output_format"], output_directory=pending["output_directory"],
            ))
            try:
                clip_path = await asyncio.shield(worker)
            except asyncio.CancelledError:
                # Cancellation must wait for the worker's result so a clip
                # created concurrently with pause/remove can be cleaned up.
                try:
                    clip_path = await asyncio.shield(worker)
                except Exception:
                    clip_path = ""
                self._discard_if_present(clip_path)
                if slot.in_flight_clips.pop(clip_id, None) is not None:
                    self._record_alert(slot, pending["keyword"], pending["transcript"], pending["mode"], pending["model"], "", 0)
                raise
            except Exception:
                # Preserve the detection even if ffmpeg invocation or filesystem
                # access fails; an empty clip path is explicit in the alert.
                clip_path = ""
            if slot.in_flight_clips.pop(clip_id, None) is None:
                # pause/remove already persisted this detection without a clip
                self._discard_if_present(clip_path)
                continue
            duration = round(sum(self._chunk_duration(path, pending["chunk_seconds"]) for path in chunks), 2)
            self._record_alert(slot, pending["keyword"], pending["transcript"], pending["mode"], pending["model"], clip_path, duration)

    @staticmethod
    def _discard_if_present(clip_path: str) -> None:
        if clip_path:
            Path(clip_path).unlink(missing_ok=True)

    @staticmethod
    def _chunk_duration(path: Path, nominal_seconds: int) -> float:
        # Captured chunks are WAV; read their headers so a short final segment
        # is reflected accurately without launching an ffprobe process.
        try:
            with wave.open(str(path), "rb") as audio:
                rate = audio.getframerate()
                return audio.getnframes() / rate if rate else float(nominal_seconds)
        except (OSError, wave.Error):
            return float(nominal_seconds)

    def _cancel_pending_clips(self, slot: MonitorSlot) -> None:
        """Persist detections on stop/pause without claiming an incomplete clip exists."""
        pending = slot.pending_clips + list(slot.in_flight_clips.values())
        slot.pending_clips = []
        slot.in_flight_clips.clear()
        for item in pending:
            self._record_alert(slot, item["keyword"], item["transcript"], item["mode"], item["model"], "", 0)

    def _record_alert(self, slot: MonitorSlot, keyword: str, transcript: str, mode_used: str, model_used: str | None, clip_path: str, duration: int | None = None) -> None:
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
            "clipDurationSeconds": duration if clip_path else 0,
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
