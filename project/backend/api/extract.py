import re

from fastapi import APIRouter, Request

from ..config import Settings
from ..schemas import (
    ErrorResponse,
    ExtractData,
    ExtractRequest,
    SuccessResponse,
    new_request_id,
)
from ..services.extract import (
    ExtractModelOutputInvalidError,
    ExtractNotConfiguredError,
    ExtractProviderError,
    ExtractProviderTimeoutError,
    extract_from_text,
)
from .errors import ApiError


router = APIRouter(tags=["extract"])

_AMBIGUOUS_ADDRESS_MARKERS = (
    "我家",
    "家里",
    "家中",
    "公司",
    "单位",
    "宿舍",
    "学校",
    "这里",
    "那边",
)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _is_ambiguous_address(value: str | None, marked_ambiguous: bool | None) -> bool:
    if marked_ambiguous is True:
        return True
    cleaned = _clean(value)
    return bool(cleaned and any(marker in cleaned for marker in _AMBIGUOUS_ADDRESS_MARKERS))


def _city_for_output(model_city: str | None, page_city: str) -> str | None:
    """Use spoken city first; use the selected page city only as a fallback."""

    return _clean(model_city) or _clean(page_city)


def _city_key(city: str) -> str:
    normalized = re.sub(r"\s+", "", city)
    return normalized.removesuffix("市")


def _normalize_category(category: str | None) -> str:
    cleaned = _clean(category)
    if not cleaned:
        return "咖啡店"
    if "咖啡" in cleaned or cleaned in {"喝咖啡", "咖啡馆"}:
        return "咖啡店"
    return cleaned


def _validate_business_output(output, *, page_city: str) -> ExtractData:
    city_a = _city_for_output(output.city_a, page_city)
    city_b = _city_for_output(output.city_b, page_city)
    address_a = _clean(output.address_a)
    address_b = _clean(output.address_b)

    if output.party_count != 2:
        raise ApiError(
            status_code=422,
            code="EXTRACT_INCOMPLETE",
            message="需要明确两个人的具体地点，请重新表达。",
            stage="extract",
        )

    if not city_a or not city_b:
        raise ApiError(
            status_code=422,
            code="EXTRACT_INCOMPLETE",
            message="请说明两个人所在的城市。",
            stage="extract",
        )

    if _is_ambiguous_address(address_a, output.address_a_ambiguous) or _is_ambiguous_address(
        address_b, output.address_b_ambiguous
    ):
        raise ApiError(
            status_code=422,
            code="EXTRACT_INCOMPLETE",
            message="请把“我家”等含糊说法替换为具体地点或地址。",
            stage="extract",
        )

    if not address_a or not address_b:
        raise ApiError(
            status_code=422,
            code="EXTRACT_INCOMPLETE",
            message="请提供两个人各自的具体地点。",
            stage="extract",
        )

    if _city_key(city_a) != _city_key(city_b):
        raise ApiError(
            status_code=422,
            code="EXTRACT_CROSS_CITY",
            message="目前只支持同一座城市内的两个地点，请重新表达。",
            stage="extract",
        )

    return ExtractData(
        city_a=city_a,
        address_a=address_a,
        city_b=city_b,
        address_b=address_b,
        category=_normalize_category(output.category),
    )


@router.post(
    "/extract",
    response_model=SuccessResponse[ExtractData],
    responses={
        422: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
    },
)
async def extract_information(
    request: Request,
    body: ExtractRequest,
) -> SuccessResponse[ExtractData]:
    if not body.text.strip() or not body.city.strip():
        raise ApiError(
            status_code=422,
            code="EXTRACT_INPUT_INVALID",
            message="text 和 city 不能为空。",
            stage="extract",
        )

    settings: Settings = request.app.state.settings
    try:
        result = await extract_from_text(
            body.text,
            body.city,
            settings=settings,
        )
    except ExtractNotConfiguredError as error:
        raise ApiError(
            status_code=503,
            code="EXTRACT_NOT_CONFIGURED",
            message="信息提取服务尚未配置，请填写 DeepSeek API Key 和接口地址。",
            stage="extract",
        ) from error
    except ExtractProviderTimeoutError as error:
        raise ApiError(
            status_code=504,
            code="EXTRACT_TIMEOUT",
            message="信息提取服务响应超时，请稍后重试。",
            stage="extract",
        ) from error
    except ExtractModelOutputInvalidError as error:
        raise ApiError(
            status_code=502,
            code="EXTRACT_MODEL_OUTPUT_INVALID",
            message="信息提取模型返回格式异常，暂时无法处理。",
            stage="extract",
        ) from error
    except ExtractProviderError as error:
        raise ApiError(
            status_code=502,
            code="EXTRACT_PROVIDER_ERROR",
            message="信息提取服务调用失败，请稍后重试。",
            stage="extract",
        ) from error

    data = _validate_business_output(result.output, page_city=body.city)
    return SuccessResponse(request_id=new_request_id(), data=data)
