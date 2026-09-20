"""Формирование тела вебхука, сериализация в JSON и подпись запроса"""

import json
from typing import Any

from payout_gateway.models import Transfer, TransferStatus
from payout_gateway.schemas import WebhookDetails, WebhookPayload, decimal_to_str
from payout_gateway.security import SIGNATURE_HEADER, generate_signature


def build_payload(transfer: Transfer) -> dict[str, Any]:
    """Тело вебхука. Вызывать только для завершённого перевода."""
    assert transfer.status in (TransferStatus.COMPLETED, TransferStatus.FAILED)
    assert transfer.from_address is not None
    payload = WebhookPayload(
        id=transfer.id,
        external_id=transfer.external_id,
        amount=decimal_to_str(transfer.amount),
        status=transfer.status,
        details=WebhookDetails(
            from_address=transfer.from_address,
            to_address=transfer.destination,
            tx_hash=transfer.tx_hash,
        ),
    )
    return payload.model_dump(mode="json")


def serialize(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


def build_request(
    payload: dict[str, Any], api_key: str
) -> tuple[bytes, dict[str, str]]:
    """Готовит (тело, заголовки). Подпись считается по ТЕМ ЖЕ байтам, что уйдут по сети."""
    body = serialize(payload)
    headers = {
        "Content-Type": "application/json",
        SIGNATURE_HEADER: generate_signature(api_key, body),
    }
    return body, headers
