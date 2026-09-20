from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from payout_gateway import service
from payout_gateway.database import get_async_session
from payout_gateway.schemas import TransferCreate, TransferResponse
from payout_gateway.security import require_token

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_token)])

SessionDep = Annotated[AsyncSession, Depends(get_async_session)]


@router.post("/transfer", response_model=TransferResponse)
async def create_transfer(
    body: TransferCreate, session: SessionDep
) -> TransferResponse:
    """
    Создать перевод.
    Повтор с тем же external_id возвращает исходный перевод (200)
    """
    transfer = await service.create_transfer(session, body)
    return TransferResponse.model_validate(transfer)
