"""CLI entrypoint — invoked by tooling/seed_iso.py and `make seed-iso`.

Full implementation in Phase 4.
"""

import argparse
from loguru import logger


def main() -> None:
    parser = argparse.ArgumentParser(description="ISO Knowledge CLI")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("seed", help="Seed ISO clauses and state template")
    args = parser.parse_args()

    if args.command == "seed":
        logger.info("Seed command — implemented in Phase 4")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
