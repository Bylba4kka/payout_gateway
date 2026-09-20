"""
Интерфейс исполнителя перевода и заглушка `MockExecutor`.
Именно здесь подключается реальная система (кошелёк, блокчейн, провайдер).
Реализован MockExecutor. Чтобы подключить настоящий, реализуйте TransferExecutor
и передайте его в payout_gateway.main.create_executor()
"""

import asyncio
import secrets
from dataclasses import dataclass
from typing import Literal, Protocol

from payout_gateway.config import settings
from payout_gateway.models import Transfer, TransferStatus


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    status: Literal[TransferStatus.COMPLETED, TransferStatus.FAILED]
    from_address: str
    tx_hash: str | None = None
    error: str | None = None


class TransferExecutor(Protocol):
    async def execute(self, transfer: Transfer) -> ExecutionResult:
        """Выполнить перевод и вернуть итог (completed/failed).

        transfer.id нужно использовать как ключ идемпотентности на стороне провайдера:
        в аварийной ситуации перевод может быть передан сюда повторно.
        Объект transfer только для чтения.
        """


class MockExecutor:
    """Заглушка: всё успешно, кроме адресов, содержащих "fail"."""

    async def execute(self, transfer: Transfer) -> ExecutionResult:
        await asyncio.sleep(0.05)  # имитация сетевого вызова
        if "fail" in transfer.destination.lower():
            return ExecutionResult(
                status=TransferStatus.FAILED,
                from_address=settings.source_wallet_address,
                error="mock: destination rejected",
            )
        return ExecutionResult(
            status=TransferStatus.COMPLETED,
            from_address=settings.source_wallet_address,
            tx_hash="0x" + secrets.token_hex(32),
        )
