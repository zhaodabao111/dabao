from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Request, UploadFile

from ..config import Settings
from ..schemas import ErrorResponse, SuccessResponse, UploadData, new_request_id
from ..services.audio_probe import (
    AudioDurationUnknownError,
    AudioProbeDependencyError,
    UnsupportedAudioError,
    probe_audio,
)
from ..services.recording_storage import RecordingStorage, StorageError
from .errors import ApiError


router = APIRouter(tags=["audio"])


class UploadTooLargeError(Exception):
    pass


async def _save_upload_with_limit(
    upload: UploadFile,
    temporary_path: Path,
    max_size_bytes: int,
) -> int:
    size = 0
    with temporary_path.open("xb") as output:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > max_size_bytes:
                raise UploadTooLargeError
            output.write(chunk)
    return size


@router.post(
    "/upload",
    response_model=SuccessResponse[UploadData],
    responses={
        413: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def upload_audio(
    request: Request,
    file: Annotated[
        UploadFile,
        File(description="WebM container with one Opus audio stream"),
    ],
) -> SuccessResponse[UploadData]:
    settings: Settings = request.app.state.settings
    temporary_path: Path | None = None

    try:
        storage = RecordingStorage(
            settings.recording_storage_dir,
            ttl_hours=settings.recording_ttl_hours,
        )
        temporary_path = storage.create_temporary_path()
        size_bytes = await _save_upload_with_limit(
            file,
            temporary_path,
            settings.audio_max_size_bytes,
        )
        probe = await probe_audio(
            temporary_path,
            ffprobe_binary=settings.ffprobe_binary,
            timeout_seconds=settings.audio_probe_timeout_seconds,
        )

        if not (
            settings.audio_min_duration_seconds
            <= probe.duration_seconds
            <= settings.audio_max_duration_seconds
        ):
            raise ApiError(
                status_code=422,
                code="AUDIO_DURATION_INVALID",
                message="录音时长必须在1—60秒之间，请重新录制。",
                stage="upload",
            )

        metadata = storage.save_recording(
            temporary_path=temporary_path,
            size_bytes=size_bytes,
            duration_seconds=probe.duration_seconds,
            container=probe.container,
            codec=probe.codec,
        )
    except UploadTooLargeError as error:
        raise ApiError(
            status_code=413,
            code="AUDIO_TOO_LARGE",
            message="录音不能超过5MB，请缩短后重新录制。",
            stage="upload",
        ) from error
    except UnsupportedAudioError as error:
        raise ApiError(
            status_code=415,
            code="UNSUPPORTED_AUDIO",
            message="仅支持 WebM/Opus 录音文件，请重新录制。",
            stage="upload",
        ) from error
    except AudioDurationUnknownError as error:
        raise ApiError(
            status_code=422,
            code="AUDIO_DURATION_INVALID",
            message="无法确认录音时长，请重新录制。",
            stage="upload",
        ) from error
    except AudioProbeDependencyError as error:
        raise ApiError(
            status_code=500,
            code="AUDIO_PROBE_UNAVAILABLE",
            message="服务器缺少音频探测工具，暂时无法接收录音。",
            stage="upload",
        ) from error
    except StorageError as error:
        raise ApiError(
            status_code=500,
            code="AUDIO_STORAGE_ERROR",
            message="录音保存失败，请稍后重试。",
            stage="upload",
        ) from error
    except OSError as error:
        raise ApiError(
            status_code=500,
            code="AUDIO_STORAGE_ERROR",
            message="录音保存失败，请稍后重试。",
            stage="upload",
        ) from error
    finally:
        await file.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return SuccessResponse(
        request_id=new_request_id(),
        data=UploadData(audio_id=metadata.audio_id),
    )
