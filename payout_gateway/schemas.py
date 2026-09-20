from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from payout_gateway.models import TransferStatus


def decimal_to_str(value: Decimal) -> str:
    return format(value.normalize(), "f")


class TransferCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    external_id: str = Field(min_length=1, max_length=255)
    currency: str = Field(min_length=1, max_length=32)
    amount: Decimal = Field(gt=0, max_digits=38, decimal_places=18)
    destination: str = Field(min_length=1, max_length=255)
    comment: str | None = Field(default=None, max_length=1000)


class TransferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    external_id: str
    currency: str
    amount: Decimal
    destination: str
    status: TransferStatus

    @field_serializer("amount")
    def _serialize_amount(self, value: Decimal) -> str:
        return decimal_to_str(value)


class WebhookDetails(BaseModel):
    from_address: str
    to_address: str
    tx_hash: str | None = None


class WebhookPayload(BaseModel):
    id: UUID
    external_id: str
    amount: str
    status: Literal[TransferStatus.COMPLETED, TransferStatus.FAILED]
    details: WebhookDetails
