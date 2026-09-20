import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from payout_gateway.database import Base


class TransferStatus(enum.StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class DeliveryStatus(enum.StrEnum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"  # исчерпали все попытки


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    # Храним как VARCHAR + CHECK, а не как нативный PG enum: проще мигрировать.
    # values_callable: в БД лежит "pending", а не "PENDING".
    return Enum(
        cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=16,
        values_callable=lambda e: [m.value for m in e],
    )


class Transfer(Base):
    __tablename__ = "transfers"
    __table_args__ = (
        # Воркер ищет только незавершённые переводы.
        Index(
            "ix_transfers_pending",
            "created_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    external_id: Mapped[str] = mapped_column(String(255), unique=True)
    currency: Mapped[str] = mapped_column(String(32))
    amount: Mapped[Decimal] = mapped_column(Numeric(38, 18))
    destination: Mapped[str] = mapped_column(String(255))
    comment: Mapped[str | None] = mapped_column(Text)

    status: Mapped[TransferStatus] = mapped_column(
        _enum(TransferStatus, "transfer_status"), default=TransferStatus.PENDING
    )
    # заполняются при завершении
    from_address: Mapped[str | None] = mapped_column(String(255))
    tx_hash: Mapped[str | None] = mapped_column(String(255))
    failure_reason: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WebhookDelivery(Base):
    """
    Запись о вебхуке создаётся в той же транзакции, что и смена статуса перевода.
    Поэтому вебхук нельзя потерять: перевод завершён <=> доставка поставлена в очередь
    """

    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        Index(
            "ix_webhook_deliveries_due",
            "next_attempt_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # один терминальный статус -> один вебхук на перевод
    transfer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transfers.id", ondelete="CASCADE"), unique=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)

    status: Mapped[DeliveryStatus] = mapped_column(
        _enum(DeliveryStatus, "delivery_status"), default=DeliveryStatus.PENDING
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
