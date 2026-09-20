import hashlib
import hmac
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from payout_gateway.config import settings

SIGNATURE_HEADER = "X-Signature"

_bearer = HTTPBearer(auto_error=False)


async def require_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    """Проверка статичного bearer-токена"""
    expected = settings.api_token.get_secret_value().encode()
    if credentials is None or not hmac.compare_digest(
        credentials.credentials.encode(), expected
    ):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def generate_signature(api_key: str, body: bytes) -> str:
    """Подпись вебхука: HMAC-SHA256(key=sha256(api_key), msg=body), hex"""
    token_hash = hashlib.sha256(api_key.encode()).digest()
    return hmac.HMAC(token_hash, body, hashlib.sha256).hexdigest()


def verify_signature(api_key: str, body: bytes, signature: str) -> bool:
    """Для стороны, принимающей вебхук и для тестов"""
    return hmac.compare_digest(generate_signature(api_key, body), signature)
