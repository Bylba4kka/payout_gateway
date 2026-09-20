"""Бизнес-логика создания перевода. Идемпотентность по `external_id`:
повторный запрос возвращает уже существующий перевод"""

import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from payout_gateway.models import Transfer
from payout_gateway.schemas import TransferCreate

logger = logging.getLogger(__name__)


async def create_transfer(session: AsyncSession, data: TransferCreate) -> Transfer:
    """
    Идемпотентное создание перевода.
    """
    statement = (
        insert(Transfer)
        .values(**data.model_dump())
        .on_conflict_do_nothing(index_elements=[Transfer.external_id])
        .returning(Transfer)
    )
    transfer = await session.scalar(statement)

    if transfer is None:  # такой external_id уже был
        transfer = await session.scalar(
            select(Transfer).where(Transfer.external_id == data.external_id)
        )
        assert transfer is not None
        if (transfer.currency, transfer.amount, transfer.destination) != (
            data.currency,
            data.amount,
            data.destination,
        ):
            # По ТЗ конфликт игнорируем и отвечаем успехом, но такое стоит видеть в логах.
            logger.warning(
                "Клиент повторно прислал external_id=%s но с другими данными",
                data.external_id,
            )

    await session.commit()
    return transfer
