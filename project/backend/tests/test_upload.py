import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.services.audio_probe import (
    AudioProbeResult,
    UnsupportedAudioError,
    probe_audio,
)


def make_client(tmp_path) -> TestClient:
    settings = Settings(
        _env_file=None,
        frontend_origin="http://localhost:5175",
        recording_storage_dir=tmp_path,
        bailian_api_key="",
        deepseek_api_key="",
        amap_api_key="",
    )
    return TestClient(create_app(settings))


async def valid_probe(*_args, **_kwargs) -> AudioProbeResult:
    return AudioProbeResult(
        container="webm",
        codec="opus",
        duration_seconds=2.5,
    )


def test_upload_saves_audio_and_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("backend.api.upload.probe_audio", valid_probe)

    with make_client(tmp_path) as client:
        response = client.post(
            "/upload",
            files={"file": ("recording.webm", b"valid-audio", "audio/webm")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"].startswith("req_")
    audio_id = payload["data"]["audio_id"]
    assert audio_id.startswith("rec_")
    assert (tmp_path / f"{audio_id}.webm").read_bytes() == b"valid-audio"

    metadata = json.loads((tmp_path / f"{audio_id}.json").read_text())
    assert metadata["audio_id"] == audio_id
    assert metadata["codec"] == "opus"
    assert metadata["duration_seconds"] == 2.5
    assert metadata["created_at"]


def test_upload_rejects_a_file_larger_than_five_mib(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("backend.api.upload.probe_audio", valid_probe)

    with make_client(tmp_path) as client:
        response = client.post(
            "/upload",
            files={
                "file": (
                    "too-large.webm",
                    b"x" * (5 * 1024 * 1024 + 1),
                    "audio/webm",
                )
            },
        )

    assert response.status_code == 413
    assert response.json()["error"] == {
        "code": "AUDIO_TOO_LARGE",
        "message": "录音不能超过5MB，请缩短后重新录制。",
        "stage": "upload",
    }
    assert list(tmp_path.iterdir()) == []


def test_upload_rejects_an_unsupported_container(tmp_path, monkeypatch) -> None:
    async def reject_probe(*_args, **_kwargs):
        raise UnsupportedAudioError

    monkeypatch.setattr("backend.api.upload.probe_audio", reject_probe)

    with make_client(tmp_path) as client:
        response = client.post(
            "/upload",
            files={"file": ("audio.mp3", b"not-webm", "audio/mpeg")},
        )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_AUDIO"


def test_upload_rejects_an_out_of_range_duration(tmp_path, monkeypatch) -> None:
    async def short_probe(*_args, **_kwargs) -> AudioProbeResult:
        return AudioProbeResult(
            container="webm",
            codec="opus",
            duration_seconds=0.5,
        )

    monkeypatch.setattr("backend.api.upload.probe_audio", short_probe)

    with make_client(tmp_path) as client:
        response = client.post(
            "/upload",
            files={"file": ("short.webm", b"short-audio", "audio/webm")},
        )

    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "AUDIO_DURATION_INVALID",
        "message": "录音时长必须在1—60秒之间，请重新录制。",
        "stage": "upload",
    }


def test_probe_uses_packet_timestamps_when_duration_metadata_is_missing(
    monkeypatch,
) -> None:
    responses = iter(
        [
            {
                "format": {"format_name": "matroska,webm"},
                "streams": [{"codec_type": "audio", "codec_name": "opus"}],
            },
            {
                "packets": [
                    {"pts_time": "-0.007", "duration_time": "0.020"},
                    {"pts_time": "1.993", "duration_time": "0.020"},
                ]
            },
        ]
    )

    async def fake_ffprobe(*_args, **_kwargs):
        return next(responses)

    monkeypatch.setattr("backend.services.audio_probe._run_ffprobe", fake_ffprobe)
    result = asyncio.run(
        probe_audio(
            Path("browser-recording.webm"),
            ffprobe_binary="ffprobe",
            timeout_seconds=10,
        )
    )

    assert result.container == "webm"
    assert result.codec == "opus"
    assert result.duration_seconds == pytest.approx(2.02)
