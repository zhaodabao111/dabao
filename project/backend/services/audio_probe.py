import asyncio
import json
import math
from dataclasses import dataclass
from pathlib import Path


class AudioProbeDependencyError(Exception):
    pass


class UnsupportedAudioError(Exception):
    pass


class AudioDurationUnknownError(Exception):
    pass


@dataclass(frozen=True)
class AudioProbeResult:
    container: str
    codec: str
    duration_seconds: float


def _positive_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


async def _run_ffprobe(
    ffprobe_binary: str,
    arguments: list[str],
    timeout_seconds: float,
) -> dict:
    try:
        process = await asyncio.create_subprocess_exec(
            ffprobe_binary,
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as error:
        raise AudioProbeDependencyError from error

    try:
        stdout, _stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds,
        )
    except TimeoutError as error:
        process.kill()
        await process.communicate()
        raise UnsupportedAudioError from error

    if process.returncode != 0:
        raise UnsupportedAudioError

    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise UnsupportedAudioError from error
    if not isinstance(payload, dict):
        raise UnsupportedAudioError
    return payload


def _duration_from_metadata(payload: dict) -> float | None:
    candidates: list[float] = []
    format_info = payload.get("format")
    if not isinstance(format_info, dict):
        format_info = {}
    format_duration = _positive_number(format_info.get("duration"))
    if format_duration is not None:
        candidates.append(format_duration)

    streams = payload.get("streams")
    if not isinstance(streams, list):
        streams = []
    for stream in streams:
        if isinstance(stream, dict) and stream.get("codec_type") == "audio":
            stream_duration = _positive_number(stream.get("duration"))
            if stream_duration is not None:
                candidates.append(stream_duration)
    return max(candidates) if candidates else None


def _duration_from_packets(payload: dict) -> float | None:
    starts: list[float] = []
    ends: list[float] = []
    packets = payload.get("packets")
    if not isinstance(packets, list):
        packets = []
    for packet in packets:
        if not isinstance(packet, dict):
            continue
        timestamp = packet.get("pts_time", packet.get("dts_time"))
        try:
            start = float(timestamp)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(start):
            continue
        packet_duration = _positive_number(packet.get("duration_time")) or 0
        starts.append(start)
        ends.append(start + packet_duration)

    if not starts or not ends:
        return None
    duration = max(ends) - min(starts)
    return duration if duration > 0 and math.isfinite(duration) else None


async def probe_audio(
    path: Path,
    *,
    ffprobe_binary: str,
    timeout_seconds: float,
) -> AudioProbeResult:
    primary = await _run_ffprobe(
        ffprobe_binary,
        [
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        timeout_seconds,
    )

    format_info = primary.get("format")
    if not isinstance(format_info, dict):
        raise UnsupportedAudioError
    format_names = {
        name.strip().lower()
        for name in str(format_info.get("format_name", "")).split(",")
        if name.strip()
    }
    streams = primary.get("streams")
    if "webm" not in format_names or not isinstance(streams, list):
        raise UnsupportedAudioError

    audio_streams = [
        stream
        for stream in streams
        if isinstance(stream, dict) and stream.get("codec_type") == "audio"
    ]
    video_streams = [
        stream
        for stream in streams
        if isinstance(stream, dict) and stream.get("codec_type") == "video"
    ]
    if (
        len(audio_streams) != 1
        or video_streams
        or str(audio_streams[0].get("codec_name", "")).lower() != "opus"
    ):
        raise UnsupportedAudioError

    duration = _duration_from_metadata(primary)
    if duration is None:
        packets = await _run_ffprobe(
            ffprobe_binary,
            [
                "-v",
                "error",
                "-print_format",
                "json",
                "-select_streams",
                "a:0",
                "-show_packets",
                "-show_entries",
                "packet=pts_time,dts_time,duration_time",
                str(path),
            ],
            timeout_seconds,
        )
        duration = _duration_from_packets(packets)
    if duration is None:
        raise AudioDurationUnknownError

    return AudioProbeResult(
        container="webm",
        codec="opus",
        duration_seconds=duration,
    )
