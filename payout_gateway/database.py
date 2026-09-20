from collections.abc import AsyncIterator, Callable
from functools import wraps

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from payout_gateway.config import settings

METADATA = MetaData(
    naming_convention={
        "all_column_names": lambda constraint, table: "_".join(
            [column.name for column in constraint.columns.values()],
        ),
        # A string mnemonic for primary key.
        "pk": "pk__%(table_name)s",
        # A string mnemonic for index.
        "ix": "ix__%(table_name)s__%(all_column_names)s",
        # A string mnemonic for foreign key.
        "fk": "fk__%(table_name)s__%(all_column_names)s__%(referred_table_name)s",
        # A string mnemonic for unique constraint.
        "uq": "uq__%(table_name)s__%(all_column_names)s",
        # A string mnemonic for check constraint.
        "ck": "ck__%(table_name)s__%(constraint_name)s",
    },
)


def transaction(func: Callable):
    """Class method decorator to control session transaction"""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        _commit = kwargs.pop("_commit", True)
        result = await func(*args, **kwargs)

        self = args[0]
        if _commit:
            await self.session.commit()
        else:
            await self.session.flush()

        return result

    return wrapper


async def get_async_session() -> AsyncIterator[AsyncSession]:
    async with async_session_maker() as session:
        yield session


engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=settings.postgres_echo,
    echo_pool=settings.postgres_echo,
)

async_session_maker = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)

Base = declarative_base(metadata=METADATA)
