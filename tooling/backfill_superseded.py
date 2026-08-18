"""One-off backfill: stamp ``superseded: False`` on existing chunks.

Retrieval now excludes chunks unless ``superseded == false`` (see
``verdeai_shared.retrieval.vector_search``). Chunks created before this field
existed have no ``superseded`` key, so they would be dropped from vector search
(``{"superseded": {"$eq": false}}`` does not match a missing field). This script
sets the field on every chunk that lacks it.

Run once after deploying the version-supersession change, e.g.:

    python -m tooling.backfill_superseded            # apply
    python -m tooling.backfill_superseded --dry-run  # count only

Note: the Atlas ``chunks_vector_idx`` must also be recreated with the new
``superseded`` / ``created_at`` filter fields for the filter to take effect —
that is a separate deployment step (drop the index; it is rebuilt at
document-processor startup via ``stage5_embed._ensure_vector_index``).
"""

import argparse
import asyncio

from verdeai_shared.db.mongo import close_client, get_database


async def _run(dry_run: bool) -> None:
    db = get_database()
    missing = {"superseded": {"$exists": False}}

    to_fix = await db.chunks.count_documents(missing)
    total = await db.chunks.count_documents({})
    print(f"chunks total={total} missing_superseded={to_fix}")

    if dry_run:
        print("dry-run: no changes written")
        return

    if to_fix == 0:
        print("nothing to backfill")
        return

    result = await db.chunks.update_many(missing, {"$set": {"superseded": False}})
    print(f"backfilled superseded=false on {result.modified_count} chunks")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill superseded flag on chunks")
    parser.add_argument("--dry-run", action="store_true", help="count only, do not write")
    args = parser.parse_args()
    try:
        asyncio.run(_run(args.dry_run))
    finally:
        asyncio.run(close_client())


if __name__ == "__main__":
    main()
