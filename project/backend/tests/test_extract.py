from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.schemas import ExtractModelOutput
from backend.services.extract import (
    ExtractModelOutputInvalidError,
    ExtractProviderTimeoutError,
    ExtractResult,
)


def make_client(tmp_path, **overrides) -> TestClient:
    values = {
        "_env_file": None,
        "frontend_origin": "http://localhost:5175",
        "deepseek_api_key": "sk-test",
        "deepseek_chat_url": "https://api.deepseek.com/chat/completions",
        "recording_storage_dir": tmp_path,
        "bailian_api_key": "",
        "amap_api_key": "",
    }
    values.update(overrides)
    return TestClient(create_app(Settings(**values)))


def model_output(**overrides) -> ExtractModelOutput:
    values = {
        "party_count": 2,
        "city_a": "杭州",
        "address_a": "杭州东站",
        "city_b": "杭州",
        "address_b": "西湖龙翔桥地铁站",
        "category": "喝咖啡",
        "incomplete_reason": None,
        "address_a_ambiguous": False,
        "address_b_ambiguous": False,
    }
    values.update(overrides)
    return ExtractModelOutput(**values)


def test_extract_returns_only_the_five_business_fields_and_normalizes_category(
    tmp_path, monkeypatch
) -> None:
    async def fake_extract(*_args, **_kwargs):
        return ExtractResult(output=model_output())

    monkeypatch.setattr("backend.api.extract.extract_from_text", fake_extract)

    with make_client(tmp_path) as client:
        response = client.post(
            "/extract",
            json={"text": "我在杭州东站，朋友在龙翔桥，想喝咖啡", "city": "杭州"},
        )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "city_a": "杭州",
        "address_a": "杭州东站",
        "city_b": "杭州",
        "address_b": "西湖龙翔桥地铁站",
        "category": "咖啡店",
    }
    assert "party_count" not in response.json()["data"]
    assert "incomplete_reason" not in response.json()["data"]


def test_extract_uses_page_city_only_when_model_did_not_say_city(
    tmp_path, monkeypatch
) -> None:
    async def fake_extract(*_args, **_kwargs):
        return ExtractResult(
            output=model_output(city_a=None, city_b=None, category=None)
        )

    monkeypatch.setattr("backend.api.extract.extract_from_text", fake_extract)

    with make_client(tmp_path) as client:
        response = client.post(
            "/extract",
            json={"text": "我在东站，朋友在西湖边", "city": "杭州"},
        )

    assert response.status_code == 200
    assert response.json()["data"]["city_a"] == "杭州"
    assert response.json()["data"]["city_b"] == "杭州"
    assert response.json()["data"]["category"] == "咖啡店"


def test_extract_rejects_incomplete_count_missing_address_vague_address_and_cross_city(
    tmp_path, monkeypatch
) -> None:
    cases = [
        (model_output(party_count=1), "EXTRACT_INCOMPLETE"),
        (model_output(address_b=None, address_b_ambiguous=True), "EXTRACT_INCOMPLETE"),
        (model_output(address_a="我家", address_a_ambiguous=True), "EXTRACT_INCOMPLETE"),
        (model_output(city_b="上海"), "EXTRACT_CROSS_CITY"),
    ]

    for output, expected_code in cases:
        async def fake_extract(*_args, output=output, **_kwargs):
            return ExtractResult(output=output)

        monkeypatch.setattr("backend.api.extract.extract_from_text", fake_extract)
        with make_client(tmp_path) as client:
            response = client.post(
                "/extract",
                json={"text": "测试口述", "city": "杭州"},
            )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == expected_code


def test_extract_keeps_model_format_error_distinct_from_business_incompleteness(
    tmp_path, monkeypatch
) -> None:
    async def invalid_output(*_args, **_kwargs):
        raise ExtractModelOutputInvalidError

    monkeypatch.setattr("backend.api.extract.extract_from_text", invalid_output)
    with make_client(tmp_path) as client:
        response = client.post(
            "/extract",
            json={"text": "格式异常测试", "city": "杭州"},
        )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "EXTRACT_MODEL_OUTPUT_INVALID"


def test_extract_maps_provider_timeout_to_504(tmp_path, monkeypatch) -> None:
    async def timeout(*_args, **_kwargs):
        raise ExtractProviderTimeoutError

    monkeypatch.setattr("backend.api.extract.extract_from_text", timeout)
    with make_client(tmp_path) as client:
        response = client.post(
            "/extract",
            json={"text": "超时测试", "city": "杭州"},
        )

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "EXTRACT_TIMEOUT"
