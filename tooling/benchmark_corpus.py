"""Load the five-company ISO 14001 benchmark corpora as fixture tenants.

The benchmark (``ISO14001_Five_Company_Benchmark_v3_MASTER``) ships five company document
sets and 190 hand-adjudicated gold labels. This creates one tenant per company, uploads that
company's documents through the real API, waits for the document pipeline to finish, and
triggers a gap analysis — so the measured result exercises the same path a customer would.

Every step goes through the public API rather than writing Mongo directly: the tenant comes
from ``POST /auth/register`` (which is what mints ``tenant_id``), and uploads carry the JWT,
so tenant isolation is exercised rather than bypassed.

Usage:
    python -m tooling.benchmark_corpus --root <path-to-MASTER> [--companies A,B] [--no-analyse]
    python -m tooling.benchmark_corpus --root <path> --status      # report only

Writes ``tooling/eval/benchmark_tenants.json`` mapping company -> tenant/analysis ids, which
``tooling/eval/export_predictions.py`` reads to build the scorer's predictions CSV.

Safe to re-run: a company already present in the manifest is reused rather than re-registered,
and documents whose filename is already uploaded for that tenant are skipped.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

# stdlib logging rather than the repo's usual loguru: this script runs on the host (it needs
# filesystem access to the benchmark bundle, which is not mounted into any container), and the
# host venv only carries httpx.
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
_log = logging.getLogger("benchmark_corpus")


class _Logger:
    """Thin shim so call sites keep the structured ``logger.info(msg, k=v)`` style."""

    @staticmethod
    def _fmt(msg: str, kw: dict[str, Any]) -> str:
        return msg + ("  " + " ".join(f"{k}={v}" for k, v in kw.items()) if kw else "")

    def info(self, msg: str, **kw: Any) -> None:
        _log.info(self._fmt(msg, kw))

    def warning(self, msg: str, **kw: Any) -> None:
        _log.warning(self._fmt(msg, kw))

    def error(self, msg: str, **kw: Any) -> None:
        _log.error(self._fmt(msg, kw))


logger = _Logger()

DEFAULT_API = "http://localhost:8000"
DEFAULT_VERSION = "iso-14001-benchmark"
MANIFEST = Path(__file__).parent / "eval" / "benchmark_tenants.json"

# Company folders in the MASTER bundle, keyed by the benchmark's own company_code.
COMPANIES = {
    "A": "A_Rivermark_Metal_Finishing",
    "B": "B_Seabrook_Dairy_Foods",
    "C": "C_ApexChem_Logistics",
    "D": "D_NovaCircuit_Electronics",
    "E": "E_Coral_Bay_Resort",
}
PASSWORD = "benchmark-fixture-pw-2026"
# Document-processor is slow (parse -> chunk -> contextualise -> embed -> index) and runs two
# replicas; a 27-document company takes a while. Poll patiently rather than failing early.
POLL_INTERVAL_S = 10
POLL_TIMEOUT_S = 3600


def company_files(root: Path, folder: str) -> list[Path]:
    """Every document for a company, de-duplicated by filename.

    Company A ships a flat ``_all/`` mirror of its category folders; the others only have the
    category folders. Taking ``_all`` when present and otherwise walking the tree yields each
    document exactly once either way.
    """
    base = root / "companies" / folder
    flat = base / "_all"
    if flat.is_dir():
        return sorted(p for p in flat.iterdir() if p.is_file())
    seen: dict[str, Path] = {}
    for p in sorted(base.rglob("*")):
        if p.is_file() and p.name not in seen:
            seen[p.name] = p
    return list(seen.values())


def load_manifest() -> dict[str, Any]:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {"api": DEFAULT_API, "version_id": DEFAULT_VERSION, "companies": {}}


def save_manifest(m: dict[str, Any]) -> None:
    """Merge into whatever is on disk rather than overwriting it.

    A long run holds its in-memory copy for many minutes while documents process. Anything
    written meanwhile — an analysis_id added by hand, or a second loader invocation for other
    companies — would otherwise be silently dropped when this run next saves.
    """
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    on_disk = load_manifest() if MANIFEST.exists() else {"companies": {}}
    merged = {**on_disk, **{k: v for k, v in m.items() if k != "companies"}}
    companies = dict(on_disk.get("companies", {}))
    for code, entry in m.get("companies", {}).items():
        companies[code] = {**companies.get(code, {}), **entry}
    merged["companies"] = companies
    MANIFEST.write_text(json.dumps(merged, indent=2), encoding="utf-8")


async def register_or_login(client: httpx.AsyncClient, code: str, folder: str) -> dict[str, str]:
    """Return {tenant_id, token} for a company, registering the tenant on first run."""
    # Not a reserved domain: email-validator rejects .local/.test/.example outright.
    email = f"benchmark-{code.lower()}@verdeai-benchmark.com"
    body = {
        "email": email,
        "password": PASSWORD,
        "first_name": "Benchmark",
        "last_name": code,
        "organisation_name": folder,
    }
    r = await client.post("/auth/register", json=body)
    if r.status_code == 201:
        tenant_id = r.json()["tenant_id"]
        logger.info("Registered benchmark tenant", company=code, tenant_id=tenant_id)
    elif r.status_code == 409:
        tenant_id = ""  # already exists; recovered from /auth/me below
        logger.info("Tenant already registered — reusing", company=code)
    else:
        raise RuntimeError(f"register failed for {code}: {r.status_code} {r.text[:300]}")

    lr = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    if lr.status_code != 200:
        raise RuntimeError(f"login failed for {code}: {lr.status_code} {lr.text[:300]}")
    token = lr.json()["access_token"]

    if not tenant_id:
        me = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        me.raise_for_status()
        tenant_id = me.json()["tenant_id"]

    return {"email": email, "tenant_id": tenant_id, "token": token}


async def upload_documents(client: httpx.AsyncClient, token: str, files: list[Path]) -> int:
    """Upload any document not already present for this tenant. Returns the number uploaded."""
    auth = {"Authorization": f"Bearer {token}"}
    existing = await client.get("/documents", headers=auth)
    existing.raise_for_status()
    have = {d.get("filename") for d in existing.json().get("items", [])}

    uploaded = 0
    for path in files:
        if path.name in have:
            continue
        with path.open("rb") as fh:
            r = await client.post(
                "/documents", headers=auth, files={"file": (path.name, fh, "application/octet-stream")}
            )
        if r.status_code in (200, 201):
            uploaded += 1
        else:
            # One unsupported file must not abort a 27-document company.
            logger.warning("Upload failed", filename=path.name, status=r.status_code, body=r.text[:200])
    return uploaded


async def wait_for_processing(client: httpx.AsyncClient, token: str, code: str) -> dict[str, int]:
    """Poll until no document is still queued/processing, or the timeout expires."""
    auth = {"Authorization": f"Bearer {token}"}
    waited = 0
    while True:
        r = await client.get("/documents", headers=auth)
        r.raise_for_status()
        docs = r.json().get("items", [])
        counts: dict[str, int] = {}
        for d in docs:
            counts[d.get("status", "unknown")] = counts.get(d.get("status", "unknown"), 0) + 1
        pending = counts.get("queued", 0) + counts.get("processing", 0)
        if pending == 0:
            logger.info("Documents settled", company=code, **counts)
            return counts
        if waited >= POLL_TIMEOUT_S:
            logger.warning("Timed out waiting for processing", company=code, pending=pending, **counts)
            return counts
        logger.info("Waiting for document processing", company=code, pending=pending, waited_s=waited)
        await asyncio.sleep(POLL_INTERVAL_S)
        waited += POLL_INTERVAL_S


async def trigger_analysis(client: httpx.AsyncClient, token: str, version_id: str) -> str | None:
    auth = {"Authorization": f"Bearer {token}"}
    r = await client.post("/analyses", headers=auth, json={"version_id": version_id, "scope": "full"})
    if r.status_code in (200, 201, 202):
        return str(r.json().get("analysis_id"))
    # 409 means one is already running for this tenant — surface it rather than starting a second.
    logger.warning("Analysis not started", status=r.status_code, body=r.text[:300])
    return None


async def run(root: Path, codes: list[str], analyse: bool, api: str, version_id: str) -> None:
    manifest = load_manifest()
    manifest["api"] = api
    manifest["version_id"] = version_id

    async with httpx.AsyncClient(base_url=api, timeout=300.0) as client:
        for code in codes:
            folder = COMPANIES[code]
            files = company_files(root, folder)
            if not files:
                logger.error("No documents found", company=code, folder=folder)
                continue

            ident = await register_or_login(client, code, folder)
            uploaded = await upload_documents(client, ident["token"], files)
            logger.info("Uploaded", company=code, uploaded=uploaded, total=len(files))

            counts = await wait_for_processing(client, ident["token"], code)

            entry = manifest["companies"].setdefault(code, {})
            entry.update(
                {
                    "company_folder": folder,
                    "email": ident["email"],
                    "tenant_id": ident["tenant_id"],
                    "documents": len(files),
                    "document_status": counts,
                }
            )

            if analyse:
                analysis_id = await trigger_analysis(client, ident["token"], version_id)
                if analysis_id:
                    entry["analysis_id"] = analysis_id
                    logger.info("Analysis started", company=code, analysis_id=analysis_id)

            save_manifest(manifest)

    save_manifest(manifest)
    logger.info("Benchmark corpus ready", manifest=str(MANIFEST), companies=list(manifest["companies"]))


async def status(api: str) -> None:
    manifest = load_manifest()
    if not manifest["companies"]:
        print("No benchmark tenants loaded yet.")
        return
    async with httpx.AsyncClient(base_url=api, timeout=60.0) as client:
        for code, e in sorted(manifest["companies"].items()):
            lr = await client.post("/auth/login", json={"email": e["email"], "password": PASSWORD})
            token = lr.json()["access_token"]
            auth = {"Authorization": f"Bearer {token}"}
            aid = e.get("analysis_id")
            state = "-"
            if aid:
                ar = await client.get(f"/analyses/{aid}", headers=auth)
                if ar.status_code == 200:
                    j = ar.json()
                    state = f"{j.get('status')} gaps={j.get('gap_count')}"
            print(f"  {code}  docs={e.get('documents')}  {e.get('document_status')}  analysis={aid or '-'}  {state}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Load the 5-company ISO 14001 benchmark corpora")
    ap.add_argument("--root", required=False, help="Path to ISO14001_Five_Company_Benchmark_v3_MASTER")
    ap.add_argument("--companies", default="A,B,C,D,E", help="Comma-separated company codes")
    ap.add_argument("--api", default=DEFAULT_API)
    ap.add_argument("--version-id", default=DEFAULT_VERSION)
    ap.add_argument("--no-analyse", action="store_true", help="Upload only; do not trigger analyses")
    ap.add_argument("--status", action="store_true", help="Report manifest state and exit")
    args = ap.parse_args()

    if args.status:
        asyncio.run(status(args.api))
        return

    if not args.root:
        raise SystemExit("--root is required unless --status is passed")

    codes = [c.strip().upper() for c in args.companies.split(",") if c.strip()]
    unknown = [c for c in codes if c not in COMPANIES]
    if unknown:
        raise SystemExit(f"Unknown company codes: {unknown}. Valid: {sorted(COMPANIES)}")

    asyncio.run(run(Path(args.root), codes, not args.no_analyse, args.api, args.version_id))


if __name__ == "__main__":
    main()
