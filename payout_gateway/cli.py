"""Единая точка входа для запуска и служебных операций.

    python -m payout_gateway run [--host H] [--port P] [--reload]   # API + фоновые воркеры
    python -m payout_gateway migrate [revision]                      # миграции БД (по умолчанию head)
"""
import argparse
from collections.abc import Sequence

import uvicorn
from alembic.config import main as alembic_main


def _run(args: argparse.Namespace) -> None:
    uvicorn.run(
        "payout_gateway.main:app", host=args.host, port=args.port, reload=args.reload
    )


def _migrate(args: argparse.Namespace) -> None:
    alembic_main(argv=["upgrade", args.revision])


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="payout_gateway")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="запустить API и фоновые воркеры")
    run.add_argument("--host", default="0.0.0.0")
    run.add_argument("--port", type=int, default=8080)
    run.add_argument(
        "--reload", action="store_true", help="автоперезагрузка (для разработки)"
    )
    run.set_defaults(handler=_run)

    migrate = sub.add_parser("migrate", help="применить миграции БД")
    migrate.add_argument("revision", nargs="?", default="head")
    migrate.set_defaults(handler=_migrate)

    args = parser.parse_args(argv)
    args.handler(args)
