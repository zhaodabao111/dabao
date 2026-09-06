import base64
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import Settings


class AsrNotConfiguredError(Exception):
    pass


class AsrBase64TooLargeError(Exception):
    pass


class AsrProviderTimeoutError(Exception):
    pass


class AsrProviderError(Exception):
    pass


class AsrInvalidResponseError(Exception):
    pass


class AsrEmptyResultError(Exception):
    pass


@dataclass(frozen=True)
class AsrResult:
    text: str


def _extract_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise AsrInvalidResponseError

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AsrInvalidResponseError
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise AsrInvalidResponseError
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise AsrInvalidResponseError

    content = message.get("content")
    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        text = "".join(parts).strip()
    else:
        raise AsrInvalidResponseError

    if not text:
        raise AsrEmptyResultError
    return text


async def recognize_audio(
    audio_bytes: bytes,
    *,
    mime_type: str,
    settings: Settings,
) -> AsrResult:
    if (
        not settings.bailian_api_key.strip()
        or not settings.bailian_asr_url.strip()
        or "{WorkspaceId}" in settings.bailian_asr_url
    ):
        raise AsrNotConfiguredError

    encoded_audio = base64.b64encode(audio_bytes)
    if len(encoded_audio) > settings.asr_max_base64_bytes:
        raise AsrBase64TooLargeError

    media_type = mime_type.split(";", maxsplit=1)[0].strip() or "audio/webm"
    data_uri = f"data:{media_type};base64,{encoded_audio.decode('ascii')}"
    payload = {
        "model": settings.bailian_asr_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": data_uri},
                    }
                ],
            }
        ],
        "stream": False,
        "asr_options": {"enable_itn": False},
    }
    headers = {
        "Authorization": f"Bearer {settings.bailian_api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.bailian_asr_timeout_seconds)
        ) as client:
            response = await client.post(
                settings.bailian_asr_url,
                headers=headers,
                json=payload,
            )
    except httpx.TimeoutException as error:
        raise AsrProviderTimeoutError from error
    except httpx.RequestError as error:
        raise AsrProviderError from error

    if response.status_code >= 400:
        raise AsrProviderError
    try:
        response_payload = response.json()
    except ValueError as error:
        raise AsrInvalidResponseError from error

    return AsrResult(text=_extract_text(response_payload))
