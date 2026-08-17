"""CLI entrypoint — `python -m app.cli seed`."""

import argparse
import asyncio

from loguru import logger

from verdeai_shared.db.repositories.iso_versions import DEFAULT_VERSION_ID

from app.config import settings
from app.decompose_requirements import run_decomposition
from app.seed_iso import run_seed


def main() -> None:
    parser = argparse.ArgumentParser(description="ISO Knowledge CLI")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("seed", help="Seed ISO clauses and state template")

    decompose_parser = subparsers.add_parser(
        "decompose-requirements", help="LLM-decompose clause requirements into atomic sub-requirements"
    )
    decompose_parser.add_argument("--version-id", default=DEFAULT_VERSION_ID)
    decompose_parser.add_argument("--dry-run", action="store_true")
    decompose_parser.add_argument("--force", action="store_true")

    args = parser.parse_args()

    if args.command == "seed":
        asyncio.run(run_seed(demo_tenant_id=settings.DEMO_TENANT_ID))
    elif args.command == "decompose-requirements":
        asyncio.run(run_decomposition(args.version_id, dry_run=args.dry_run, force=args.force))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
