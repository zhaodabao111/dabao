from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.services.asr import (
    AsrEmptyResultError,
    AsrResult,
    AsrProviderTimeoutError,
)
from backend.services.recording_storage import RecordingStorage


def make_settings(tmp_path, **overrides) -> Settings:
    values = {
        "_env_file": None,
        "frontend_origin": "http://localhost:5175",
        "recording_storage_dir": tmp_path,
        "bailian_api_key": "sk-test",
        "bailian_asr_url": "https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions",
        "deepseek_api_key": "",
        "amap_api_key": "",
    }
    values.update(overrides)
    return Settings(**values)


def seed_recording(tmp_path, content: bytes = b"webm-audio") -> str:
    storage = RecordingStorage(tmp_path)
    temporary_path = storage.create_temporary_path()
    temporary_path.write_bytes(content)
    metadata = storage.save_recording(
        temporary_path=temporary_path,
        size_bytes=len(content),
        duration_seconds=2,
        container="webm",
        codec="opus",
    )
    return metadata.audio_id


def test_asr_returns_provider_text_for_an_unexpired_audio_id(tmp_path, monkeypatch) -> None:
    audio_id = seed_recording(tmp_path)
    settings = make_settings(tmp_path)

    async def fake_recognize_audio(audio_bytes, *, mime_type, settings):
        assert audio_bytes == b"webm-audio"
        assert mime_type == "audio/webm;codecs=opus"
        return AsrResult(text="我在杭州东站，朋友在西湖龙翔桥地铁站")

    monkeypatch.setattr("backend.api.asr.recognize_audio", fake_recognize_audio)

    with TestClient(create_app(settings)) as client:
        response = client.post("/asr", json={"audio_id": audio_id})

    assert response.status_code == 200
    assert response.json()["data"] == {
        "text": "我在杭州东站，朋友在西湖龙翔桥地铁站"
    }


def test_asr_rejects_unknown_audio_id_without_calling_provider(tmp_path, monkeypatch) -> None:
    settings = make_settings(tmp_path)

    async def unexpected_call(*_args, **_kwargs):
        raise AssertionError("provider must not be called")

    monkeypatch.setattr("backend.api.asr.recognize_audio", unexpected_call)

    with TestClient(create_app(settings)) as client:
        response = client.post("/asr", json={"audio_id": "rec_" + "0" * 32})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "AUDIO_NOT_FOUND"


def test_asr_reports_missing_configuration_without_calling_provider(tmp_path) -> None:
    audio_id = seed_recording(tmp_path)
    settings = make_settings(tmp_path, bailian_api_key="")

    with TestClient(create_app(settings)) as client:
        response = client.post("/asr", json={"audio_id": audio_id})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ASR_NOT_CONFIGURED"


def test_asr_maps_empty_result_and_timeout_to_unified_errors(tmp_path, monkeypatch) -> None:
    audio_id = seed_recording(tmp_path)
    settings = make_settings(tmp_path)

    async def empty_result(*_args, **_kwargs):
        raise AsrEmptyResultError

    monkeypatch.setattr("backend.api.asr.recognize_audio", empty_result)
    with TestClient(create_app(settings)) as client:
        empty_response = client.post("/asr", json={"audio_id": audio_id})

    assert empty_response.status_code == 422
    assert empty_response.json()["error"]["code"] == "ASR_EMPTY_RESULT"

    async def timeout(*_args, **_kwargs):
        raise AsrProviderTimeoutError

    monkeypatch.setattr("backend.api.asr.recognize_audio", timeout)
    with TestClient(create_app(settings)) as client:
        timeout_response = client.post("/asr", json={"audio_id": audio_id})

    assert timeout_response.status_code == 504
    assert timeout_response.json()["error"]["code"] == "ASR_TIMEOUT"


def test_asr_base64_limit_is_checked_before_provider_request(tmp_path) -> None:
    audio_id = seed_recording(tmp_path)
    settings = make_settings(tmp_path, asr_max_base64_bytes=1)

    with TestClient(create_app(settings)) as client:
        response = client.post("/asr", json={"audio_id": audio_id})

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "ASR_AUDIO_TOO_LARGE"
