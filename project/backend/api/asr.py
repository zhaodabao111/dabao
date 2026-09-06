from fastapi import APIRouter, Request

from ..config import Settings
from ..schemas import AsrData, AsrRequest, ErrorResponse, SuccessResponse, new_request_id
from ..services.asr import (
    AsrBase64TooLargeError,
    AsrEmptyResultError,
    AsrInvalidResponseError,
    AsrNotConfiguredError,
    AsrProviderError,
    AsrProviderTimeoutError,
    recognize_audio,
)
from ..services.recording_storage import RecordingStorage
from .errors import ApiError


router = APIRouter(tags=["audio"])


@router.post(
    "/asr",
    response_model=SuccessResponse[AsrData],
    responses={
        404: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def transcribe_audio(
    request: Request,
    body: AsrRequest,
) -> SuccessResponse[AsrData]:
    settings: Settings = request.app.state.settings
    try:
        storage = RecordingStorage(
            settings.recording_storage_dir,
            ttl_hours=settings.recording_ttl_hours,
        )
        loaded_audio = storage.load_audio(body.audio_id)
    except OSError as error:
        raise ApiError(
            status_code=500,
            code="AUDIO_STORAGE_ERROR",
            message="录音读取失败，请稍后重试。",
            stage="asr",
        ) from error
    if loaded_audio is None:
        raise ApiError(
            status_code=404,
            code="AUDIO_NOT_FOUND",
            message="录音不存在或已过期，请重新上传录音。",
            stage="asr",
        )

    metadata, audio_bytes = loaded_audio
    try:
        result = await recognize_audio(
            audio_bytes,
            mime_type=metadata.mime_type,
            settings=settings,
        )
    except AsrBase64TooLargeError as error:
        raise ApiError(
            status_code=413,
            code="ASR_AUDIO_TOO_LARGE",
            message="录音编码后超过语音识别服务的大小限制。",
            stage="asr",
        ) from error
    except AsrEmptyResultError as error:
        raise ApiError(
            status_code=422,
            code="ASR_EMPTY_RESULT",
            message="没有识别到有效语音，请重新录音。",
            stage="asr",
        ) from error
    except AsrNotConfiguredError as error:
        raise ApiError(
            status_code=503,
            code="ASR_NOT_CONFIGURED",
            message="语音识别服务尚未配置，请填写百炼北京地域配置。",
            stage="asr",
        ) from error
    except AsrProviderTimeoutError as error:
        raise ApiError(
            status_code=504,
            code="ASR_TIMEOUT",
            message="语音识别服务响应超时，请稍后重试。",
            stage="asr",
        ) from error
    except AsrInvalidResponseError as error:
        raise ApiError(
            status_code=502,
            code="ASR_INVALID_RESPONSE",
            message="语音识别服务返回了无法解析的结果。",
            stage="asr",
        ) from error
    except AsrProviderError as error:
        raise ApiError(
            status_code=502,
            code="ASR_PROVIDER_ERROR",
            message="语音识别服务调用失败，请稍后重试。",
            stage="asr",
        ) from error

    return SuccessResponse(
        request_id=new_request_id(),
        data=AsrData(text=result.text),
    )
