"""One-time (re-runnable) generation of slot schemas for each ISO clause.

A clause's ``requirements`` prose says what the standard demands; a ``slot_schema`` says what
*information must exist* for that demand to be fulfilled, one slot per required piece, each
carrying its own detailed extraction question and its own fill rules. See
``verdeai_shared.iso.slots`` for the shape and for why this lives in data rather than in the
analyser's prompt.

The schema is company-blind — it names no document, tenant or evidence source — so it is
generated once per ISO version and reused by every analysis. The gap-analyzer prefers it when
present and otherwise synthesizes one from ``requirements_list``, so this script is a quality
upgrade, not a hard dependency.

Usage:
    python -m app.generate_slot_schemas [--version-id ID] [--dry-run] [--force] [--clause-id ID]

Safe to re-run: clauses that already have a ``slot_schema`` are skipped unless --force.
--dry-run prints the proposed schema without writing, so the extraction questions can be read
and the prompt corrected before 38 clauses are generated against it — a weak schema silently
degrades every analysis that follows.
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
from verdeai_shared.iso.slots import ClauseSlotSchema
from verdeai_shared.llm.structured import StructuredOutputError, stream_structured
from verdeai_shared.settings import settings

_PROMPTS_DIR = __import__("pathlib").Path(_vs_pkg.__file__).parent / "llm" / "prompts"
_jinja = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)


async def generate_slots(clause: dict[str, object]) -> list[dict[str, object]]:
    clause_id = str(clause.get("clause_id", ""))
    clause_title = str(clause.get("title", clause_id))
    clause_requirements = str(clause.get("requirements", ""))

    system_prompt = _jinja.get_template("generate_slots_system.j2").render()
    user_prompt = _jinja.get_template("generate_slots_user.j2").render(
        clause_id=clause_id,
        clause_title=clause_title,
        clause_requirements=clause_requirements,
    )
    # The primary model, not the cheap one: this runs once per ISO version and its output is
    # the fixed input to every analysis afterwards.
    result = await stream_structured(
        model=settings.PRIMARY_REASONING_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        schema=ClauseSlotSchema,
        max_tokens=4096,
        name="generate_slot_schema",
    )
    return [slot.model_dump() for slot in result.slots]


_AUTHORED_PATH = __import__("pathlib").Path(__file__).parent / "data" / "benchmark_slot_schemas.json"


def load_authored_schemas(path: object = None) -> dict[str, list[dict[str, object]]]:
    """Load hand-authored slot schemas, keyed by clause_id.

    These are written directly from the normative text of ISO 14001:2015, with ``required``
    set false only where the standard itself conditions the obligation ("as appropriate",
    "where applicable", "if practicable"). Generation is useful for clauses the standard
    already states as an enumerated list, but it over-decomposes prose clauses and guesses
    at modality — and ``required`` is what the analyser's verdict is derived from, so it is
    worth having under review in git rather than regenerated per run.
    """
    import json as _json
    import pathlib

    p = pathlib.Path(str(path)) if path else _AUTHORED_PATH
    return _json.loads(p.read_text(encoding="utf-8"))


async def apply_authored_schemas(
    version_id: str = DEFAULT_VERSION_ID,
    *,
    path: object = None,
    dry_run: bool = False,
) -> None:
    """Write the hand-authored schemas onto a version's clauses, no LLM involved."""
    db = get_database()
    repo = ISOClausesRepository(db)
    authored = load_authored_schemas(path)
    existing = {str(c.get("clause_id", "")) for c in await repo.list_all(version_id=version_id)}

    missing = sorted(set(authored) - existing)
    unauthored = sorted(existing - set(authored))
    if missing:
        logger.warning("Authored clauses absent from this version — skipped", clause_ids=missing)
    if unauthored:
        # Parent headings (6.1, 7.4, ...) carry no normative text of their own; their verdicts
        # come from deterministic parent aggregation, so they are authored nowhere.
        logger.info("Version clauses with no authored schema", clause_ids=unauthored)

    for cid, slots in authored.items():
        if cid not in existing:
            continue
        if dry_run:
            print(f"\n=== {cid} ===")
            print(json.dumps(slots, indent=2))
            continue
        await repo.upsert({"clause_id": cid, "version_id": version_id, "slot_schema": slots})
        required = sum(1 for s in slots if s.get("required"))
        logger.info("Applied authored slot schema", clause_id=cid, slots=len(slots), required=required)

    logger.info(
        "Authored slot schemas applied",
        version_id=version_id,
        clauses=len(set(authored) & existing),
        dry_run=dry_run,
    )


async def run_generation(
    version_id: str = DEFAULT_VERSION_ID,
    *,
    dry_run: bool = False,
    force: bool = False,
    clause_id: str | None = None,
) -> None:
    db = get_database()
    repo = ISOClausesRepository(db)
    clauses = await repo.list_all(version_id=version_id)
    if clause_id:
        clauses = [c for c in clauses if str(c.get("clause_id", "")) == clause_id]

    logger.info(
        "Generating clause slot schemas",
        version_id=version_id,
        total=len(clauses),
        dry_run=dry_run,
    )

    for clause in clauses:
        cid = clause.get("clause_id", "")
        if not force and clause.get("slot_schema"):
            logger.info("Skipping (already has slot_schema)", clause_id=cid)
            continue

        try:
            slots = await generate_slots(clause)
        except StructuredOutputError as exc:
            logger.error("Slot generation failed — leaving clause unchanged", clause_id=cid, error=str(exc))
            continue

        if dry_run:
            print(f"\n=== {cid} — {clause.get('title', '')} ===")
            print(json.dumps(slots, indent=2))
            continue

        await repo.upsert({"clause_id": cid, "version_id": version_id, "slot_schema": slots})
        required = sum(1 for s in slots if s.get("required"))
        logger.info("Generated slot schema", clause_id=cid, slots=len(slots), required=required)

    logger.info("Slot schema generation complete", version_id=version_id, dry_run=dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate slot-filling schemas for ISO clauses")
    parser.add_argument("--version-id", default=DEFAULT_VERSION_ID)
    parser.add_argument("--dry-run", action="store_true", help="Print proposed schemas without writing")
    parser.add_argument("--force", action="store_true", help="Regenerate clauses that already have slot_schema")
    parser.add_argument("--clause-id", default=None, help="Generate for a single clause only")
    parser.add_argument(
        "--authored",
        nargs="?",
        const=True,
        default=None,
        metavar="PATH",
        help="Apply hand-authored schemas from data/benchmark_slot_schemas.json (or PATH) instead of calling the LLM",
    )
    args = parser.parse_args()

    if args.authored:
        asyncio.run(
            apply_authored_schemas(
                args.version_id,
                path=None if args.authored is True else args.authored,
                dry_run=args.dry_run,
            )
        )
        return

    asyncio.run(
        run_generation(
            args.version_id,
            dry_run=args.dry_run,
            force=args.force,
            clause_id=args.clause_id,
        )
    )


if __name__ == "__main__":
    main()
