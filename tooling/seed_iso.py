"""ISO seeding script — invoked by `make seed-iso`.

Delegates to the iso-knowledge service CLI.
Full implementation in Phase 4.
"""

import subprocess
import sys


def main() -> None:
    print("Running ISO knowledge seed via iso-knowledge service CLI...")
    subprocess.run(
        ["python", "-m", "app.cli", "seed"],
        cwd="/app/service",
        check=True,
    )


if __name__ == "__main__":
    main()
