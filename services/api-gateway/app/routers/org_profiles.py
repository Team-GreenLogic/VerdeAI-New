"""Org profiles endpoints — a tenant can own multiple org profiles."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from verdeai_shared.auth.tenant import CurrentPrincipal
from verdeai_shared.db.mongo import get_database
from verdeai_shared.db.repositories.iso_clauses import ISOClausesRepository
from verdeai_shared.db.repositories.iso_state import ISOStateRepository
from verdeai_shared.db.repositories.iso_versions import DEFAULT_VERSION_ID
from verdeai_shared.db.repositories.org_profile import OrgProfileRepository
from verdeai_shared.db.repositories.org_profiles import OrgProfilesRepository

router = APIRouter(prefix="/org-profiles", tags=["org-profiles"])


# --- Pydantic models ---

class OrgProfileCreate(BaseModel):
    org_name: str | None = None
    org_industry: str | None = None
    org_size: str | None = None
    org_location: str | None = None
    description: str | None = None


class OrgProfileUpdate(OrgProfileCreate):
    pass


class OrgProfileOut(OrgProfileCreate):
    profile_id: str
    created_at: datetime
    updated_at: datetime


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


def _to_out(doc: dict[str, Any]) -> OrgProfileOut:
    return OrgProfileOut(
        profile_id=str(doc["_id"]),
        org_name=doc.get("org_name"),
        org_industry=doc.get("org_industry"),
        org_size=doc.get("org_size"),
        org_location=doc.get("org_location"),
        description=doc.get("description"),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


async def _get_owned_profile(db: Any, tenant_id: str, profile_id: str) -> dict[str, Any]:
    """Fetch an org profile doc, raise 404 if not found or not owned by tenant.

    ``OrgProfilesRepository.get`` always filters by tenant_id, so a foreign-tenant
    profile_id 404s exactly like a nonexistent one — no cross-tenant existence leak.
    """
    profile = await OrgProfilesRepository(db, tenant_id).get(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Org profile not found")
    return profile


# --- Registry endpoints ---

@router.get("", response_model=list[OrgProfileOut])
async def list_org_profiles(principal: CurrentPrincipal) -> list[OrgProfileOut]:
    """List all org profiles owned by the current tenant."""
    db = get_database()
    profiles = await OrgProfilesRepository(db, principal.tenant_id).list_all()
    return [_to_out(p) for p in profiles]


@router.post("", response_model=OrgProfileOut, status_code=status.HTTP_201_CREATED)
async def create_org_profile(
    body: OrgProfileCreate,
    principal: CurrentPrincipal,
) -> OrgProfileOut:
    """Create a new org profile for the current tenant."""
    db = get_database()
    doc = await OrgProfilesRepository(db, principal.tenant_id).create(body.model_dump())
    return _to_out(doc)


@router.get("/{profile_id}", response_model=OrgProfileOut)
async def get_org_profile(
    profile_id: str,
    principal: CurrentPrincipal,
) -> OrgProfileOut:
    """Get a single org profile."""
    db = get_database()
    profile = await _get_owned_profile(db, principal.tenant_id, profile_id)
    return _to_out(profile)


@router.put("/{profile_id}", response_model=OrgProfileOut)
async def update_org_profile(
    profile_id: str,
    body: OrgProfileUpdate,
    principal: CurrentPrincipal,
) -> OrgProfileOut:
    """Update an org profile's summary fields (only provided fields are changed)."""
    db = get_database()
    await _get_owned_profile(db, principal.tenant_id, profile_id)
    updated = await OrgProfilesRepository(db, principal.tenant_id).update(
        profile_id, body.model_dump(exclude_none=True)
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Org profile not found")
    return _to_out(updated)


@router.delete("/{profile_id}", status_code=status.HTTP_200_OK)
async def delete_org_profile(
    profile_id: str,
    principal: CurrentPrincipal,
) -> dict[str, str]:
    """Soft-delete a profile while preserving all of its associated tenant data."""
    db = get_database()
    tenant_id = principal.tenant_id
    await _get_owned_profile(db, tenant_id, profile_id)

    deleted = await OrgProfilesRepository(db, tenant_id).soft_delete(profile_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Org profile not found")

    return {"profile_id": profile_id, "status": "deleted"}


# --- Per-clause structured field endpoints (ClauseFieldsTab mechanism) ---

@router.get("/{profile_id}/completeness", response_model=CompletenessReport)
async def get_completeness(
    profile_id: str,
    principal: CurrentPrincipal,
    version_id: str = Query(default=DEFAULT_VERSION_ID),
) -> CompletenessReport:
    """Return overall and per-clause profile completeness percentages."""
    db = get_database()
    tenant_id = principal.tenant_id
    await _get_owned_profile(db, tenant_id, profile_id)

    clauses = await ISOClausesRepository(db).list_all(version_id=version_id)
    state_entries = await ISOStateRepository(db).list_all(version_id=version_id)
    org_entries = await OrgProfileRepository(db, tenant_id, profile_id, version_id=version_id).list_all()

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


@router.get("/{profile_id}/clauses", response_model=list[ClauseSummary])
async def list_clause_summaries(
    profile_id: str,
    principal: CurrentPrincipal,
    version_id: str = Query(default=DEFAULT_VERSION_ID),
) -> list[ClauseSummary]:
    """List all ISO clauses with their profile completeness."""
    report = await get_completeness(profile_id, principal, version_id=version_id)
    return report.clauses


@router.get("/{profile_id}/clauses/{clause_id}", response_model=ClauseProfile)
async def get_clause_profile(
    profile_id: str,
    clause_id: str,
    principal: CurrentPrincipal,
    version_id: str = Query(default=DEFAULT_VERSION_ID),
) -> ClauseProfile:
    """Get all state fields for a clause, with current profile values."""
    db = get_database()
    tenant_id = principal.tenant_id
    await _get_owned_profile(db, tenant_id, profile_id)

    clause = await ISOClausesRepository(db).get(clause_id, version_id=version_id)
    if not clause:
        raise HTTPException(status_code=404, detail=f"Clause '{clause_id}' not found")

    state_entries = await ISOStateRepository(db).list_for_clause(clause_id, version_id=version_id)
    org_entries = await OrgProfileRepository(
        db, tenant_id, profile_id, version_id=version_id
    ).list_for_clause(clause_id)
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


@router.put("/{profile_id}/clauses/{clause_id}", response_model=ClauseProfile)
async def update_clause_profile(
    profile_id: str,
    clause_id: str,
    body: dict[str, Any],
    principal: CurrentPrincipal,
    version_id: str = Query(default=DEFAULT_VERSION_ID),
) -> ClauseProfile:
    """Update per-clause state field values. Body is a flat field_path → value map."""
    db = get_database()
    tenant_id = principal.tenant_id
    await _get_owned_profile(db, tenant_id, profile_id)

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
        await OrgProfileRepository(db, tenant_id, profile_id, version_id=version_id).upsert_many(to_upsert)

    # Return updated clause profile
    return await get_clause_profile(profile_id, clause_id, principal, version_id=version_id)
