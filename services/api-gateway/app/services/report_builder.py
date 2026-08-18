"""Compliance report generation — assembles analysis data and renders a PDF.

Gathers a completed analysis (results, recommendations, missing requirements) plus
the tenant's org profile and the ISO standard metadata, computes an overall compliance
score, and renders a print-ready PDF via a Jinja2 HTML template + WeasyPrint.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import markdown as _markdown
import nh3
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from verdeai_shared.db.repositories.iso_clauses import ISOClausesRepository
from verdeai_shared.db.repositories.iso_versions import DEFAULT_VERSION_ID, ISOVersionsRepository
from verdeai_shared.db.repositories.org_profile import OrgProfileRepository

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_jinja = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "j2"]),
)

# Maps the flat org_profile field_path values to friendly report keys.
_ORG_FIELDS: dict[str, str] = {
    "name": "org.name",
    "industry": "org.industry",
    "size": "org.size",
    "location": "org.location",
    "primary_activities": "org.primary_activities",
    "leadership_roles": "org.leadership_roles",
}

# decision -> css class used by the template for RAG colouring
_DECISION_CLASS = {
    "Met": "met",
    "Partially Met": "partial",
    "Not Met": "notmet",
    "Insufficient Evidence": "insufficient",
}

# Citation excerpts come from LlamaParse-parsed document chunks, which for
# complex tables often embed raw HTML (<table><tr><td>...) inline in the
# markdown text. Render + sanitize to a narrow allowlist so tables show up
# properly in the PDF instead of as literal escaped tags.
_CITATION_ALLOWED_TAGS = {
    "p", "br", "strong", "em", "b", "i", "ul", "ol", "li",
    "table", "thead", "tbody", "tr", "th", "td",
    "code", "pre", "blockquote", "h1", "h2", "h3", "h4", "a",
}
_CITATION_ALLOWED_ATTRIBUTES = {
    "a": {"href"},
    "td": {"colspan", "rowspan", "align"},
    "th": {"colspan", "rowspan", "align"},
}


def _citation_html(text: str) -> Markup:
    """Render a citation excerpt to sanitized HTML safe for the report template."""
    if not text:
        return Markup("")
    html = _markdown.markdown(text, extensions=["tables"])
    clean = nh3.clean(html, tags=_CITATION_ALLOWED_TAGS, attributes=_CITATION_ALLOWED_ATTRIBUTES)
    return Markup(clean)


def _clause_sort_key(clause_id: str) -> list[int]:
    """Numeric sort for dotted clause ids (e.g. "6.1.2") — mirrors the UI's compareClauseIds."""
    parts: list[int] = []
    for p in str(clause_id).split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return parts


def _citation_label(c: dict[str, Any]) -> str:
    if c.get("type") == "org_profile":
        return c.get("field_path") or "Organisation Profile"
    filename = c.get("filename") or c.get("chunk_id") or "Document"
    page = c.get("page")
    return f"{filename} p.{page}" if page not in (None, "") else str(filename)


def _score_label(score: float) -> str:
    if score >= 80:
        return "Strong"
    if score >= 50:
        return "Moderate"
    return "Needs Improvement"


async def build_report_context(
    db: Any,
    tenant_id: str,
    analysis: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the full template context for the compliance report."""
    analysis_id = analysis["analysis_id"]
    version_id = analysis.get("version_id", DEFAULT_VERSION_ID)

    # --- Standard metadata ---
    version_doc = await ISOVersionsRepository(db).get(version_id) or {}
    standard = {
        "version_id": version_id,
        "name": version_doc.get("name", version_id),
        "description": version_doc.get("description", ""),
    }

    # --- Org profile (report header) ---
    org_entries = await OrgProfileRepository(db, tenant_id, version_id=version_id).list_all()
    value_map = {doc["field_path"]: doc.get("value") for doc in org_entries}
    org = {key: (value_map.get(path) or None) for key, path in _ORG_FIELDS.items()}

    # --- Clause catalog (titles + sections) ---
    clause_docs = await ISOClausesRepository(db).list_all(version_id=version_id)
    clause_meta = {
        c["clause_id"]: {"title": c.get("title", c["clause_id"]), "section": c.get("section", "")}
        for c in clause_docs
    }

    # --- Per-clause results / recommendations / missing requirements ---
    results = await db.result_store.find(
        {"analysis_id": analysis_id, "tenant_id": tenant_id}
    ).to_list(length=None)
    recs = await db.recommendation_store.find(
        {"analysis_id": analysis_id, "tenant_id": tenant_id}
    ).to_list(length=None)
    missing = await db.missing_request_store.find(
        {"analysis_id": analysis_id, "tenant_id": tenant_id}
    ).to_list(length=None)

    recs_by_clause: dict[str, list[dict[str, Any]]] = {}
    for r in recs:
        recs_by_clause.setdefault(r["clause_id"], []).append({
            "text": r.get("text", ""),
            "cost": int(r.get("cost", 0) or 0),
            "impact": int(r.get("impact", 0) or 0),
            "effort_weeks": r.get("effort_weeks", 0),
        })

    missing_by_clause: dict[str, list[dict[str, Any]]] = {}
    for m in missing:
        missing_by_clause.setdefault(m["clause_id"], []).append({
            "field_path": m.get("field_path", ""),
            "request_text": m.get("request_text", ""),
        })

    # --- Assemble clause rows + counts ---
    counts = {"Met": 0, "Partially Met": 0, "Not Met": 0, "Insufficient Evidence": 0, "Other": 0}
    clauses: list[dict[str, Any]] = []
    for r in results:
        cid = r["clause_id"]
        decision = r.get("decision", "Unknown")
        counts[decision if decision in counts else "Other"] += 1
        meta = clause_meta.get(cid, {"title": cid, "section": ""})
        clauses.append({
            "clause_id": cid,
            "title": meta["title"],
            "section": meta["section"],
            "decision": decision,
            "decision_class": _DECISION_CLASS.get(decision, "other"),
            "confidence_pct": round((r.get("confidence", 0.0) or 0.0) * 100),
            "reasoning": r.get("reasoning", ""),
            "missing_evidence": r.get("missing_evidence", []) or [],
            "citations": [
                {"label": _citation_label(c), "html": _citation_html(c.get("text", ""))}
                for c in (r.get("citations", []) or [])
            ],
            "recommendations": recs_by_clause.get(cid, []),
            "missing_requirements": missing_by_clause.get(cid, []),
            "is_gap": decision != "Met",
        })

    clauses.sort(key=lambda c: _clause_sort_key(c["clause_id"]))

    total = len(clauses)
    met = counts["Met"]
    score = round(met / total * 100) if total else 0
    gap_count = analysis.get("gap_count")
    if gap_count is None:
        gap_count = total - met

    summary = {
        "total": total,
        "met": met,
        "partially_met": counts["Partially Met"],
        "not_met": counts["Not Met"],
        "insufficient": counts["Insufficient Evidence"],
        "other": counts["Other"],
        "gap_count": gap_count,
        "score": score,
        "score_label": _score_label(score),
    }

    created_at = analysis.get("created_at")
    return {
        "org": org,
        "standard": standard,
        "analysis": {
            "id": analysis_id,
            "short_id": analysis_id[:8],
            "created_at": _fmt_date(created_at),
        },
        "generated_at": _fmt_date(datetime.now(timezone.utc)),
        "summary": summary,
        "clauses": clauses,
        # convenience subsets for the template
        "gap_clauses": [c for c in clauses if c["is_gap"]],
        "clauses_with_recs": [c for c in clauses if c["recommendations"]],
        "clauses_with_missing": [c for c in clauses if c["missing_requirements"]],
    }


def _fmt_date(dt: Any) -> str:
    if isinstance(dt, datetime):
        return dt.strftime("%d %B %Y")
    return str(dt) if dt else "—"


def render_report_pdf(context: dict[str, Any]) -> bytes:
    """Render the report context to PDF bytes via the Jinja2 template + WeasyPrint."""
    # Imported lazily so the module (and its tests) can load without the native libs.
    from weasyprint import HTML

    html = _jinja.get_template("compliance_report.html.j2").render(**context)
    return HTML(string=html).write_pdf()
