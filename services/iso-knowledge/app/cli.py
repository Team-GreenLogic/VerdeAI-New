"""CLI entrypoint — `python -m app.cli seed`."""

import argparse
import asyncio

from loguru import logger

from app.config import settings
from app.seed_iso import run_seed


def main() -> None:
    parser = argparse.ArgumentParser(description="ISO Knowledge CLI")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("seed", help="Seed ISO clauses and state template")
    args = parser.parse_args()

    if args.command == "seed":
        asyncio.run(run_seed(demo_tenant_id=settings.DEMO_TENANT_ID))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
