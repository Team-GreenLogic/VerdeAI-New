"""Org profile endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from fastapi import Query

from verdeai_shared.auth.tenant import CurrentPrincipal
from verdeai_shared.db.mongo import get_database
from verdeai_shared.db.repositories.iso_clauses import ISOClausesRepository
from verdeai_shared.db.repositories.iso_state import ISOStateRepository
from verdeai_shared.db.repositories.iso_versions import DEFAULT_VERSION_ID
from verdeai_shared.db.repositories.org_profile import OrgProfileRepository

router = APIRouter(prefix="/org-profile", tags=["org-profile"])

# Top-level org field paths
_ORG_FIELDS: dict[str, str] = {
    "org_name": "org.name",
    "org_industry": "org.industry",
    "org_size": "org.size",
    "org_location": "org.location",
    "primary_activities": "org.primary_activities",
    "leadership_roles": "org.leadership_roles",
}


# --- Pydantic models ---

class OrgProfile(BaseModel):
    org_name: str | None = None
    org_industry: str | None = None
    org_size: str | None = None
    org_location: str | None = None
    primary_activities: str | None = None
    leadership_roles: str | None = None


class OrgProfileUpdate(BaseModel):
    org_name: str | None = None
    org_industry: str | None = None
    org_size: str | None = None
    org_location: str | None = None
    primary_activities: str | None = None
    leadership_roles: str | None = None


class FieldValue(BaseModel):
    field_path: str
    label: str
    field_type: str
    value: Any | None = None
    default: Any | None = None


class ClauseProfile(BaseModel):
    clause_id: str
    title: str
    fields: list[FieldValue]


class ClauseSummary(BaseModel):
    clause_id: str
    title: str
    filled: int
    total: int
    pct: float


class CompletenessReport(BaseModel):
    overall_pct: float
    clauses: list[ClauseSummary]


# --- Helpers ---

def _pct(filled: int, total: int) -> float:
    return round(filled / total * 100, 1) if total else 0.0


# --- Endpoints ---

@router.get("", response_model=OrgProfile)
async def get_org_profile(
    principal: CurrentPrincipal,
    version_id: str = Query(default=DEFAULT_VERSION_ID),
) -> OrgProfile:
    """Return the tenant's top-level organisation profile."""
    db = get_database()
    repo = OrgProfileRepository(db, principal.tenant_id, version_id=version_id)
    all_fields = await repo.list_all()
    value_map = {doc["field_path"]: doc.get("value") for doc in all_fields}
    return OrgProfile(**{
        key: value_map.get(path)
        for key, path in _ORG_FIELDS.items()
    })


@router.put("", response_model=OrgProfile)
async def update_org_profile(
    body: OrgProfileUpdate,
    principal: CurrentPrincipal,
    version_id: str = Query(default=DEFAULT_VERSION_ID),
) -> OrgProfile:
    """Update top-level organisation profile fields (only provided fields are changed)."""
    db = get_database()
    repo = OrgProfileRepository(db, principal.tenant_id, version_id=version_id)

    updates = {
        _ORG_FIELDS[key]: value
        for key, value in body.model_dump(exclude_none=True).items()
        if key in _ORG_FIELDS
    }
    if updates:
        await repo.upsert_many(updates)

    # Return updated state
    all_fields = await repo.list_all()
    value_map = {doc["field_path"]: doc.get("value") for doc in all_fields}
    return OrgProfile(**{
        key: value_map.get(path)
        for key, path in _ORG_FIELDS.items()
    })


@router.get("/completeness", response_model=CompletenessReport)
async def get_completeness(
    principal: CurrentPrincipal,
    version_id: str = Query(default=DEFAULT_VERSION_ID),
) -> CompletenessReport:
    """Return overall and per-clause profile completeness percentages."""
    db = get_database()
    tenant_id = principal.tenant_id

    clauses = await ISOClausesRepository(db).list_all(version_id=version_id)
    state_entries = await ISOStateRepository(db).list_all(version_id=version_id)
    org_entries = await OrgProfileRepository(db, tenant_id, version_id=version_id).list_all()

    filled_paths = {doc["field_path"] for doc in org_entries if doc.get("value") not in (None, "", [])}

    # Group state fields by clause
    clause_fields: dict[str, list[str]] = {}
    for entry in state_entries:
        cid = entry.get("clause_id", "")
        clause_fields.setdefault(cid, []).append(entry["field_path"])

    clause_map = {c["clause_id"]: c.get("title", c["clause_id"]) for c in clauses}

    summaries: list[ClauseSummary] = []
    total_all = 0
    filled_all = 0

    for cid in sorted(clause_map):
        fields = clause_fields.get(cid, [])
        total = len(fields)
        filled = sum(1 for fp in fields if fp in filled_paths)
        total_all += total
        filled_all += filled
        summaries.append(ClauseSummary(
            clause_id=cid,
            title=clause_map[cid],
            filled=filled,
            total=total,
            pct=_pct(filled, total),
        ))

    return CompletenessReport(
        overall_pct=_pct(filled_all, total_all),
        clauses=summaries,
    )


@router.get("/clauses", response_model=list[ClauseSummary])
async def list_clause_summaries(
    principal: CurrentPrincipal,
    version_id: str = Query(default=DEFAULT_VERSION_ID),
) -> list[ClauseSummary]:
    """List all ISO clauses with their profile completeness."""
    report = await get_completeness(principal, version_id=version_id)
    return report.clauses


@router.get("/clauses/{clause_id}", response_model=ClauseProfile)
async def get_clause_profile(
    clause_id: str,
    principal: CurrentPrincipal,
    version_id: str = Query(default=DEFAULT_VERSION_ID),
) -> ClauseProfile:
    """Get all state fields for a clause, with current tenant values."""
    db = get_database()
    tenant_id = principal.tenant_id

    clause = await ISOClausesRepository(db).get(clause_id, version_id=version_id)
    if not clause:
        raise HTTPException(status_code=404, detail=f"Clause '{clause_id}' not found")

    state_entries = await ISOStateRepository(db).list_for_clause(clause_id, version_id=version_id)
    org_entries = await OrgProfileRepository(db, tenant_id, version_id=version_id).list_for_clause(clause_id)
    value_map = {doc["field_path"]: doc.get("value") for doc in org_entries}

    fields = [
        FieldValue(
            field_path=e["field_path"],
            label=e.get("label", e["field_path"]),
            field_type=e.get("field_type", "text"),
            value=value_map.get(e["field_path"]),
            default=e.get("default"),
        )
        for e in state_entries
    ]

    return ClauseProfile(
        clause_id=clause_id,
        title=clause.get("title", clause_id),
        fields=fields,
    )


@router.put("/clauses/{clause_id}", response_model=ClauseProfile)
async def update_clause_profile(
    clause_id: str,
    body: dict[str, Any],
    principal: CurrentPrincipal,
    version_id: str = Query(default=DEFAULT_VERSION_ID),
) -> ClauseProfile:
    """Update per-clause state field values. Body is a flat field_path → value map."""
    db = get_database()
    tenant_id = principal.tenant_id

    clause = await ISOClausesRepository(db).get(clause_id, version_id=version_id)
    if not clause:
        raise HTTPException(status_code=404, detail=f"Clause '{clause_id}' not found")

    # Validate that submitted field_paths belong to this clause
    state_entries = await ISOStateRepository(db).list_for_clause(clause_id, version_id=version_id)
    valid_paths = {e["field_path"] for e in state_entries}

    to_upsert = {fp: val for fp, val in body.items() if fp in valid_paths}
    invalid = set(body.keys()) - valid_paths
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown field paths for clause {clause_id}: {sorted(invalid)}",
        )

    if to_upsert:
        await OrgProfileRepository(db, tenant_id, version_id=version_id).upsert_many(to_upsert)

    # Return updated clause profile
    return await get_clause_profile(clause_id, principal, version_id=version_id)
