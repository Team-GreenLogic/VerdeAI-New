"""One-time (re-runnable) LLM decomposition of clause requirements into atomic sub-requirements.

Each ``iso_clauses`` document stores its normative text as one prose ``requirements`` blob.
This script asks the LLM to split that prose into a validated list of atomic, individually
checkable obligations (``requirements_list``), persisted back onto the clause document.
The gap-analyzer pipeline prefers this curated list when present, falling back to a
deterministic sentence-split (``verdeai_shared.iso.requirements.naive_decompose_requirements``)
otherwise — so this script is a quality upgrade, not a hard dependency.

Usage:
    python -m app.decompose_requirements [--version-id ID] [--dry-run] [--force]

Safe to re-run: by default, clauses that already have a ``requirements_list`` are skipped.
Pass --force to regenerate everyone. --dry-run prints the proposed decomposition without writing,
so results are hand-reviewable before committing to the database.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from jinja2 import Environment, FileSystemLoader
from loguru import logger

import verdeai_shared as _vs_pkg
from verdeai_shared.db.mongo import get_database
from verdeai_shared.db.repositories.iso_clauses import ISOClausesRepository
from verdeai_shared.db.repositories.iso_versions import DEFAULT_VERSION_ID
from verdeai_shared.iso.requirements import SubRequirementList
from verdeai_shared.llm.structured import StructuredOutputError, stream_structured
from verdeai_shared.settings import settings

_PROMPTS_DIR = __import__("pathlib").Path(_vs_pkg.__file__).parent / "llm" / "prompts"
_jinja = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)


async def decompose_clause(clause: dict[str, object]) -> list[dict[str, str]]:
    clause_id = str(clause.get("clause_id", ""))
    clause_title = str(clause.get("title", clause_id))
    clause_requirements = str(clause.get("requirements", ""))

    system_prompt = _jinja.get_template("decompose_requirements_system.j2").render()
    user_prompt = _jinja.get_template("decompose_requirements_user.j2").render(
        clause_id=clause_id,
        clause_title=clause_title,
        clause_requirements=clause_requirements,
    )
    result = await stream_structured(
        model=settings.CHEAP_REASONING_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        schema=SubRequirementList,
        max_tokens=2048,
        name="decompose_requirements",
    )
    return [item.model_dump() for item in result.items]


async def run_decomposition(
    version_id: str = DEFAULT_VERSION_ID,
    *,
    dry_run: bool = False,
    force: bool = False,
) -> None:
    db = get_database()
    repo = ISOClausesRepository(db)
    clauses = await repo.list_all(version_id=version_id)

    logger.info("Decomposing clause requirements", version_id=version_id, total=len(clauses), dry_run=dry_run)

    for clause in clauses:
        clause_id = clause.get("clause_id", "")
        if not force and clause.get("requirements_list"):
            logger.info("Skipping (already decomposed)", clause_id=clause_id)
            continue

        try:
            items = await decompose_clause(clause)
        except StructuredOutputError as exc:
            logger.error("Decomposition failed — leaving clause unchanged", clause_id=clause_id, error=str(exc))
            continue

        if dry_run:
            print(f"\n=== {clause_id} ===")
            print(json.dumps(items, indent=2))
            continue

        await repo.upsert({"clause_id": clause_id, "version_id": version_id, "requirements_list": items})
        logger.info("Decomposed clause", clause_id=clause_id, sub_requirements=len(items))

    logger.info("Decomposition complete", version_id=version_id, dry_run=dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description="Decompose ISO clause requirements into atomic sub-requirements")
    parser.add_argument("--version-id", default=DEFAULT_VERSION_ID)
    parser.add_argument("--dry-run", action="store_true", help="Print proposed decomposition without writing")
    parser.add_argument("--force", action="store_true", help="Regenerate clauses that already have requirements_list")
    args = parser.parse_args()

    asyncio.run(run_decomposition(args.version_id, dry_run=args.dry_run, force=args.force))


if __name__ == "__main__":
    main()
