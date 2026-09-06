import json
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from ..config import Settings
from ..prompts.extract import EXTRACT_SYSTEM_PROMPT, build_extract_user_prompt
from ..schemas import ExtractModelOutput


class ExtractNotConfiguredError(Exception):
    pass


class ExtractProviderTimeoutError(Exception):
    pass


class ExtractProviderError(Exception):
    pass


class ExtractModelOutputInvalidError(Exception):
    pass


@dataclass(frozen=True)
class ExtractResult:
    output: ExtractModelOutput


def _parse_model_output(payload: Any) -> ExtractModelOutput:
    if not isinstance(payload, dict):
        raise ExtractModelOutputInvalidError
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ExtractModelOutputInvalidError
    choice = choices[0]
    if not isinstance(choice, dict):
        raise ExtractModelOutputInvalidError
    message = choice.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise ExtractModelOutputInvalidError
    content = message["content"].strip()
    if not content:
        raise ExtractModelOutputInvalidError
    try:
        decoded = json.loads(content)
        return ExtractModelOutput.model_validate(decoded)
    except (json.JSONDecodeError, TypeError, ValidationError) as error:
        raise ExtractModelOutputInvalidError from error


async def extract_from_text(
    text: str,
    city: str,
    *,
    settings: Settings,
) -> ExtractResult:
    if not settings.deepseek_api_key.strip() or not settings.deepseek_chat_url.strip():
        raise ExtractNotConfiguredError

    payload = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_extract_user_prompt(text, city),
            },
        ],
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "stream": False,
        "max_tokens": 800,
    }
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.deepseek_extract_timeout_seconds)
        ) as client:
            response = await client.post(
                settings.deepseek_chat_url,
                headers=headers,
                json=payload,
            )
    except httpx.TimeoutException as error:
        raise ExtractProviderTimeoutError from error
    except httpx.RequestError as error:
        raise ExtractProviderError from error

    if response.status_code >= 400:
        raise ExtractProviderError
    try:
        response_payload = response.json()
    except ValueError as error:
        raise ExtractModelOutputInvalidError from error
    return ExtractResult(output=_parse_model_output(response_payload))
