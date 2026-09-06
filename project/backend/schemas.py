from typing import Generic, Literal, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, StrictStr


DataT = TypeVar("DataT")


class SuccessResponse(BaseModel, Generic[DataT]):
    request_id: str
    data: DataT


class HealthData(BaseModel):
    status: Literal["ok"]


class UploadData(BaseModel):
    audio_id: str


class AsrRequest(BaseModel):
    audio_id: str


class AsrData(BaseModel):
    text: str


class ExtractRequest(BaseModel):
    text: StrictStr
    city: StrictStr


class ExtractModelOutput(BaseModel):
    """Internal JSON contract returned by DeepSeek; not exposed directly."""

    model_config = ConfigDict(extra="forbid")

    party_count: StrictInt | None
    city_a: StrictStr | None
    address_a: StrictStr | None
    city_b: StrictStr | None
    address_b: StrictStr | None
    category: StrictStr | None
    incomplete_reason: StrictStr | None
    address_a_ambiguous: StrictBool | None
    address_b_ambiguous: StrictBool | None


class ExtractData(BaseModel):
    city_a: str
    address_a: str
    city_b: str
    address_b: str
    category: str


class ErrorBody(BaseModel):
    code: str
    message: str
    stage: str


class ErrorResponse(BaseModel):
    request_id: str
    error: ErrorBody


def new_request_id() -> str:
    return f"req_{uuid4().hex}"
