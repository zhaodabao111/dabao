from typing import Generic, Literal, TypeVar
from uuid import uuid4

from pydantic import BaseModel


DataT = TypeVar("DataT")


class SuccessResponse(BaseModel, Generic[DataT]):
    request_id: str
    data: DataT


class HealthData(BaseModel):
    status: Literal["ok"]


def new_request_id() -> str:
    return f"req_{uuid4().hex}"
