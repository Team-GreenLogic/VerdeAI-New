"""Synthetic corpus generator — creates fixture tenants for testing.

Full implementation in Phase 4+.
"""

import argparse
from loguru import logger


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic test fixtures")
    parser.add_argument("--tenants", type=int, default=3, help="Number of tenants to generate")
    args = parser.parse_args()
    logger.info(f"Generating {args.tenants} synthetic tenants — implemented in Phase 4")


if __name__ == "__main__":
    main()
