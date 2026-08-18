"""ISO 14001:2015 knowledge seeder.

Populates:
  - iso_clauses        (32 sub-clauses with embeddings)
  - iso_state_template (3 state fields per clause)
  - org_profile        (blank entries for demo tenant)
  - iso_clauses_vector_idx  (Atlas Vector Search index)
  - the benchmark version (``data/benchmark_clauses.json``) as a separate
    published ISO version — see ``seed_benchmark_version``

Safe to re-run — all writes are idempotent upserts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from verdeai_shared.db.mongo import get_database
from verdeai_shared.db.repositories.iso_clauses import ISOClausesRepository
from verdeai_shared.db.repositories.iso_state import ISOStateRepository
from verdeai_shared.db.repositories.iso_versions import DEFAULT_VERSION_ID, ISOVersionsRepository
from verdeai_shared.iso.state_template import STANDARD_STATE_FIELDS
from verdeai_shared.retrieval.embedder import embed_documents
from verdeai_shared.settings import settings

# ---------------------------------------------------------------------------
# ISO 14001:2015 clause catalog — 32 sub-clauses
# ---------------------------------------------------------------------------

CLAUSES: list[dict[str, Any]] = [
    # ── Section 4 — Context of the organization ──────────────────────────
    {
        "clause_id": "4.1",
        "section": 4,
        "title": "Understanding the organization and its context",
        "requirements": (
            "The organization shall determine external and internal issues that are relevant "
            "to its purpose and that affect its ability to achieve the intended outcomes of its "
            "environmental management system. Such issues shall include environmental conditions "
            "being affected by or capable of affecting the organization. The organization shall "
            "monitor and review information about these external and internal issues."
        ),
        "keywords": ["context", "external issues", "internal issues", "environmental conditions", "monitoring"],
    },
    {
        "clause_id": "4.2",
        "section": 4,
        "title": "Understanding the needs and expectations of interested parties",
        "requirements": (
            "The organization shall determine the interested parties that are relevant to the "
            "environmental management system, and the relevant needs and expectations (i.e. "
            "requirements) of these interested parties, and which of these needs and expectations "
            "become its compliance obligations. The organization shall monitor and review "
            "information about these interested parties and their relevant requirements."
        ),
        "keywords": ["interested parties", "stakeholders", "compliance obligations", "needs", "expectations"],
    },
    {
        "clause_id": "4.3",
        "section": 4,
        "title": "Determining the scope of the environmental management system",
        "requirements": (
            "The organization shall determine the boundaries and applicability of the environmental "
            "management system to establish its scope. When determining this scope, the organization "
            "shall consider the external and internal issues referred to in 4.1, the compliance "
            "obligations referred to in 4.2, and its organizational units, functions and physical "
            "boundaries, its activities, products and services, and its authority and ability to "
            "exercise control and influence. The scope shall be maintained as documented information "
            "and be available to interested parties."
        ),
        "keywords": ["scope", "boundaries", "applicability", "documented information", "organizational units"],
    },
    {
        "clause_id": "4.4",
        "section": 4,
        "title": "Environmental management system",
        "requirements": (
            "To achieve the intended outcomes, including enhancing its environmental performance, "
            "the organization shall establish, implement, maintain and continually improve an "
            "environmental management system, including the processes needed and their interactions, "
            "in accordance with the requirements of this International Standard. The organization "
            "shall consider the knowledge gained in 4.1 and 4.2 when establishing and maintaining "
            "the environmental management system."
        ),
        "keywords": ["EMS", "establish", "implement", "maintain", "continually improve", "processes"],
    },
    # ── Section 5 — Leadership ────────────────────────────────────────────
    {
        "clause_id": "5.1",
        "section": 5,
        "title": "Leadership and commitment",
        "requirements": (
            "Top management shall demonstrate leadership and commitment with respect to the "
            "environmental management system by taking accountability for the effectiveness of "
            "the EMS, ensuring that the environmental policy and objectives are established and "
            "compatible with the strategic direction of the organization, ensuring the integration "
            "of the EMS requirements into the organization's business processes, ensuring that the "
            "resources needed for the EMS are available, communicating the importance of effective "
            "environmental management and conforming to EMS requirements, ensuring that the EMS "
            "achieves its intended outcomes, directing persons to contribute to the effectiveness "
            "of the EMS, promoting continual improvement, and supporting other relevant management "
            "roles to demonstrate their leadership as it applies to their areas of responsibility."
        ),
        "keywords": ["top management", "leadership", "commitment", "accountability", "resources", "continual improvement"],
    },
    {
        "clause_id": "5.2",
        "section": 5,
        "title": "Environmental policy",
        "requirements": (
            "Top management shall establish, implement and maintain an environmental policy that, "
            "within the defined scope of its EMS, provides a framework for setting environmental "
            "objectives, includes a commitment to the protection of the environment including "
            "prevention of pollution and other specific commitments relevant to the context of the "
            "organization, includes a commitment to fulfil its compliance obligations, includes a "
            "commitment to continual improvement of the EMS to enhance environmental performance. "
            "The environmental policy shall be maintained as documented information, communicated "
            "within the organization, and be available to interested parties."
        ),
        "keywords": ["environmental policy", "protection", "pollution prevention", "compliance", "documented information"],
    },
    {
        "clause_id": "5.3",
        "section": 5,
        "title": "Organizational roles, responsibilities and authorities",
        "requirements": (
            "Top management shall ensure that the responsibilities and authorities for relevant "
            "roles are assigned and communicated within the organization. Top management shall "
            "assign the responsibility and authority for ensuring that the EMS conforms to the "
            "requirements of this International Standard and for reporting on the performance of "
            "the EMS, including environmental performance, to top management."
        ),
        "keywords": ["roles", "responsibilities", "authorities", "assigned", "reporting", "performance"],
    },
    # ── Section 6 — Planning ──────────────────────────────────────────────
    {
        "clause_id": "6.1.1",
        "section": 6,
        "title": "Actions to address risks and opportunities — General",
        "requirements": (
            "When planning for the EMS, the organization shall consider the issues referred to in "
            "4.1, the requirements referred to in 4.2, and the scope of its EMS, and shall "
            "determine the risks and opportunities that need to be addressed to give assurance "
            "that the EMS can achieve its intended outcomes, prevent or reduce undesired effects "
            "including the potential for external environmental conditions to affect the "
            "organization, and achieve continual improvement. The organization shall maintain "
            "documented information of its risks and opportunities and processes needed to "
            "address them."
        ),
        "keywords": ["risks", "opportunities", "planning", "undesired effects", "documented information"],
    },
    {
        "clause_id": "6.1.2",
        "section": 6,
        "title": "Environmental aspects",
        "requirements": (
            "Within the defined scope of the EMS, the organization shall determine the "
            "environmental aspects of its activities, products and services that it can control "
            "and those that it can influence, and their associated environmental impacts, "
            "considering a life cycle perspective. The organization shall determine those aspects "
            "that have or can have a significant environmental impact (i.e. significant "
            "environmental aspects) using established criteria. The organization shall communicate "
            "its significant environmental aspects among the various levels and functions of the "
            "organization. The organization shall maintain documented information."
        ),
        "keywords": ["environmental aspects", "environmental impacts", "significant", "life cycle", "activities", "products", "services"],
    },
    {
        "clause_id": "6.1.3",
        "section": 6,
        "title": "Compliance obligations",
        "requirements": (
            "The organization shall determine and have access to the compliance obligations "
            "related to its environmental aspects. The organization shall determine how these "
            "compliance obligations apply to the organization and shall take these compliance "
            "obligations into account when establishing, implementing, maintaining and continually "
            "improving its EMS. The organization shall maintain documented information of its "
            "compliance obligations."
        ),
        "keywords": ["compliance obligations", "legal requirements", "access", "applicable", "documented information"],
    },
    {
        "clause_id": "6.1.4",
        "section": 6,
        "title": "Planning action",
        "requirements": (
            "The organization shall plan to take actions to address its significant environmental "
            "aspects, compliance obligations and risks and opportunities identified in 6.1.1–6.1.3. "
            "The organization shall plan how to integrate and implement the actions into its EMS "
            "processes or other business processes, and evaluate the effectiveness of these actions. "
            "When planning these actions, the organization shall consider its technological options "
            "and its financial, operational and business requirements."
        ),
        "keywords": ["planning action", "integrate", "implement", "effectiveness", "technological options"],
    },
    {
        "clause_id": "6.2.1",
        "section": 6,
        "title": "Environmental objectives — General",
        "requirements": (
            "The organization shall establish environmental objectives at relevant functions and "
            "levels, taking into account the organization's significant environmental aspects and "
            "associated compliance obligations, and considering its risks and opportunities. "
            "Environmental objectives shall be consistent with the environmental policy, "
            "measurable if practicable, monitored, communicated, and updated as appropriate. "
            "The organization shall maintain documented information on the environmental objectives."
        ),
        "keywords": ["environmental objectives", "measurable", "monitored", "communicated", "documented information"],
    },
    {
        "clause_id": "6.2.2",
        "section": 6,
        "title": "Planning actions to achieve environmental objectives",
        "requirements": (
            "When planning how to achieve its environmental objectives, the organization shall "
            "determine what will be done, what resources will be required, who will be responsible, "
            "when it will be completed, and how the results will be evaluated, including indicators "
            "for monitoring progress toward achievement of its measurable environmental objectives. "
            "The organization shall consider how actions to achieve its environmental objectives "
            "can be integrated into the organization's business processes."
        ),
        "keywords": ["achieve objectives", "resources", "responsible", "timeline", "indicators", "monitoring progress"],
    },
    # ── Section 7 — Support ───────────────────────────────────────────────
    {
        "clause_id": "7.1",
        "section": 7,
        "title": "Resources",
        "requirements": (
            "The organization shall determine and provide the resources needed for the "
            "establishment, implementation, maintenance and continual improvement of the "
            "environmental management system."
        ),
        "keywords": ["resources", "determine", "provide", "establishment", "continual improvement"],
    },
    {
        "clause_id": "7.2",
        "section": 7,
        "title": "Competence",
        "requirements": (
            "The organization shall determine the necessary competence of person(s) doing work "
            "under its control that affects its environmental performance and its ability to fulfil "
            "its compliance obligations, ensure that these persons are competent on the basis of "
            "appropriate education, training, or experience, determine training needs associated "
            "with its environmental aspects and its EMS, and take actions to acquire the necessary "
            "competence and evaluate the effectiveness of the actions taken. The organization shall "
            "retain appropriate documented information as evidence of competence."
        ),
        "keywords": ["competence", "training", "education", "experience", "documented information", "effectiveness"],
    },
    {
        "clause_id": "7.3",
        "section": 7,
        "title": "Awareness",
        "requirements": (
            "The organization shall ensure that persons doing work under the organization's control "
            "are aware of the environmental policy, the significant environmental aspects and "
            "related actual or potential environmental impacts associated with their work, their "
            "contribution to the effectiveness of the EMS including the benefits of enhanced "
            "environmental performance, and the implications of not conforming with EMS requirements "
            "including not fulfilling the organization's compliance obligations."
        ),
        "keywords": ["awareness", "environmental policy", "significant aspects", "contribution", "implications"],
    },
    {
        "clause_id": "7.4",
        "section": 7,
        "title": "Communication",
        "requirements": (
            "The organization shall establish, implement and maintain the process(es) needed for "
            "internal and external communications relevant to the EMS, including on what it will "
            "communicate, when to communicate, with whom to communicate, how to communicate, and "
            "who communicates. When establishing its communication process(es), the organization "
            "shall take into account its compliance obligations and ensure that environmental "
            "information communicated is consistent and reliable."
        ),
        "keywords": ["communication", "internal", "external", "process", "reliable", "consistent"],
    },
    {
        "clause_id": "7.5.1",
        "section": 7,
        "title": "Documented information — General",
        "requirements": (
            "The organization's EMS shall include documented information required by this "
            "International Standard and documented information determined by the organization "
            "as being necessary for the effectiveness of the EMS. The extent of documented "
            "information for an EMS can differ from one organization to another due to the size "
            "of the organization and its type of activities, products and services, the need to "
            "demonstrate fulfilment of its compliance obligations, and the complexity of processes "
            "and their interactions."
        ),
        "keywords": ["documented information", "required", "effectiveness", "complexity", "fulfilment"],
    },
    {
        "clause_id": "7.5.2",
        "section": 7,
        "title": "Creating and updating documented information",
        "requirements": (
            "When creating and updating documented information, the organization shall ensure "
            "appropriate identification and description (e.g. a title, date, author, or reference "
            "number), format (e.g. language, software version, graphics) and media (e.g. paper, "
            "electronic), and review and approval for suitability and adequacy."
        ),
        "keywords": ["creating", "updating", "identification", "format", "review", "approval", "documented information"],
    },
    {
        "clause_id": "7.5.3",
        "section": 7,
        "title": "Control of documented information",
        "requirements": (
            "Documented information required by the EMS and by this International Standard shall "
            "be controlled to ensure it is available and suitable for use, where and when it is "
            "needed, and it is adequately protected (e.g. from loss of confidentiality, improper "
            "use, or loss of integrity). For the control of documented information, the "
            "organization shall address distribution, access, retrieval and use, storage and "
            "preservation, control of changes, and retention and disposition."
        ),
        "keywords": ["control", "available", "protected", "distribution", "access", "storage", "retention"],
    },
    # ── Section 8 — Operation ─────────────────────────────────────────────
    {
        "clause_id": "8.1",
        "section": 8,
        "title": "Operational planning and control",
        "requirements": (
            "The organization shall establish, implement, control and maintain the processes "
            "needed to meet the requirements for the provision of products and services and to "
            "implement the actions determined in clause 6, by establishing operating criteria for "
            "the processes, and implementing control of the processes in accordance with the "
            "operating criteria. The organization shall control planned changes and review the "
            "consequences of unintended changes, taking action to mitigate any adverse effects "
            "as necessary. The organization shall ensure that outsourced processes are controlled "
            "or influenced and shall communicate relevant environmental requirements to external "
            "providers, including contractors, using a life cycle perspective."
        ),
        "keywords": ["operational control", "operating criteria", "outsourced", "life cycle", "external providers", "contractors"],
    },
    {
        "clause_id": "8.2",
        "section": 8,
        "title": "Emergency preparedness and response",
        "requirements": (
            "The organization shall establish, implement and maintain the process(es) needed to "
            "prepare for and respond to potential emergency situations identified in 6.1.1. "
            "The organization shall plan actions to prevent or mitigate adverse environmental "
            "impacts from emergency situations, respond to actual emergency situations, take "
            "action to prevent or mitigate the consequences of emergency situations, periodically "
            "test the planned response actions where practicable, periodically review and revise "
            "the process and planned response actions after testing and after emergency situations, "
            "and provide relevant information and training related to emergency preparedness and "
            "response to relevant interested parties including persons working under its control."
        ),
        "keywords": ["emergency preparedness", "response", "prevention", "mitigate", "testing", "training", "interested parties"],
    },
    # ── Section 9 — Performance evaluation ───────────────────────────────
    {
        "clause_id": "9.1.1",
        "section": 9,
        "title": "Monitoring, measurement, analysis and evaluation — General",
        "requirements": (
            "The organization shall monitor, measure, analyse and evaluate its environmental "
            "performance. The organization shall determine what needs to be monitored and measured, "
            "the methods for monitoring, measurement, analysis and evaluation, as applicable, to "
            "ensure valid results, the criteria against which the organization will evaluate its "
            "environmental performance and appropriate indicators, when the monitoring and measuring "
            "shall be performed, and when the results from monitoring and measurement shall be "
            "analysed and evaluated. The organization shall ensure that calibrated or verified "
            "monitoring and measurement equipment is used and maintained. The organization shall "
            "retain appropriate documented information as evidence of the monitoring, measurement, "
            "analysis and evaluation results."
        ),
        "keywords": ["monitoring", "measurement", "analysis", "evaluation", "indicators", "calibrated", "documented information"],
    },
    {
        "clause_id": "9.1.2",
        "section": 9,
        "title": "Evaluation of compliance",
        "requirements": (
            "The organization shall establish, implement and maintain the process(es) needed to "
            "evaluate fulfilment of its compliance obligations. The organization shall determine "
            "the frequency that compliance will be evaluated, evaluate compliance and take action "
            "if needed, maintain knowledge and understanding of its compliance status, and retain "
            "documented information as evidence of the compliance evaluation results."
        ),
        "keywords": ["compliance evaluation", "frequency", "fulfilment", "compliance status", "documented information"],
    },
    {
        "clause_id": "9.2.1",
        "section": 9,
        "title": "Internal audit — General",
        "requirements": (
            "The organization shall conduct internal audits at planned intervals to provide "
            "information on whether the environmental management system conforms to the "
            "organization's own requirements for its EMS, to the requirements of this "
            "International Standard, and is effectively implemented and maintained."
        ),
        "keywords": ["internal audit", "planned intervals", "conformance", "effectively implemented"],
    },
    {
        "clause_id": "9.2.2",
        "section": 9,
        "title": "Internal audit programme",
        "requirements": (
            "The organization shall establish, implement and maintain an audit programme(s) "
            "including the frequency, methods, responsibilities, planning requirements and "
            "reporting of its internal audits. When establishing the audit programme, the "
            "organization shall take into consideration the environmental importance of the "
            "processes concerned, changes affecting the organization, and the results of previous "
            "audits. The organization shall define the audit criteria and scope for each audit, "
            "select auditors and conduct audits to ensure objectivity and impartiality of the "
            "audit process, ensure that the results of the audits are reported to relevant "
            "management, and retain documented information as evidence of the audit programme "
            "and the audit results."
        ),
        "keywords": ["audit programme", "frequency", "methods", "responsibilities", "audit criteria", "objectivity", "documented information"],
    },
    {
        "clause_id": "9.3",
        "section": 9,
        "title": "Management review",
        "requirements": (
            "Top management shall review the organization's EMS at planned intervals to ensure "
            "its continuing suitability, adequacy and effectiveness. The management review shall "
            "include consideration of the status of actions from previous management reviews, "
            "changes in external and internal issues relevant to the EMS including environmental "
            "aspects, compliance obligations, risks and opportunities, the degree to which "
            "environmental objectives have been achieved, information on the organization's "
            "environmental performance including trends in nonconformities and corrective actions, "
            "monitoring and measurement results, fulfilment of compliance obligations, audit "
            "results, adequacy of resources, relevant communications from interested parties "
            "including complaints, and opportunities for continual improvement. The outputs of "
            "the management review shall include conclusions on the continuing suitability, "
            "adequacy and effectiveness of the EMS, decisions related to continual improvement "
            "opportunities, and any need for changes to the EMS, including resource needs."
        ),
        "keywords": ["management review", "top management", "suitability", "adequacy", "effectiveness", "continual improvement"],
    },
    # ── Section 10 — Improvement ──────────────────────────────────────────
    {
        "clause_id": "10.1",
        "section": 10,
        "title": "General",
        "requirements": (
            "The organization shall determine opportunities for improvement and implement "
            "necessary actions to achieve the intended outcomes of its environmental management "
            "system."
        ),
        "keywords": ["improvement", "opportunities", "intended outcomes", "actions"],
    },
    {
        "clause_id": "10.2",
        "section": 10,
        "title": "Nonconformity and corrective action",
        "requirements": (
            "When a nonconformity occurs, the organization shall react to the nonconformity "
            "and, as applicable, take action to control and correct it, deal with the "
            "consequences, including mitigating adverse environmental impacts, evaluate the "
            "need for action to eliminate the causes of the nonconformity in order that it does "
            "not recur or occur elsewhere, implement any action needed, review the effectiveness "
            "of any corrective action taken, make changes to the EMS if necessary. Corrective "
            "actions shall be appropriate to the significance of the effects of the "
            "nonconformities encountered, including the environmental impacts. The organization "
            "shall retain documented information as evidence of the nature of the nonconformities "
            "and any subsequent actions taken, and the results of any corrective action."
        ),
        "keywords": ["nonconformity", "corrective action", "root cause", "recurrence", "effectiveness", "documented information"],
    },
    {
        "clause_id": "10.3",
        "section": 10,
        "title": "Continual improvement",
        "requirements": (
            "The organization shall continually improve the suitability, adequacy and "
            "effectiveness of the environmental management system to enhance environmental "
            "performance. The organization shall consider the outputs of the analysis and "
            "evaluation process referred to in 9.1.1, the outputs of the management review "
            "referred to in 9.3, to confirm that continual improvement is being implemented."
        ),
        "keywords": ["continual improvement", "suitability", "adequacy", "effectiveness", "environmental performance"],
    },
]

# ---------------------------------------------------------------------------
# State template fields per clause
# ---------------------------------------------------------------------------

_STATE_FIELDS = STANDARD_STATE_FIELDS


# ---------------------------------------------------------------------------
# Seeding functions
# ---------------------------------------------------------------------------

async def ensure_iso_vector_index(db: Any) -> None:
    """Create iso_clauses_vector_idx if not already present (idempotent)."""
    index_name = settings.ISO_VECTOR_INDEX_NAME
    try:
        existing = await db.iso_clauses.list_search_indexes().to_list(length=None)
        names = [idx.get("name") for idx in existing]
        if index_name in names:
            logger.info("ISO vector index already exists", index=index_name)
            return
        await db.iso_clauses.create_search_index(
            {
                "name": index_name,
                "type": "vectorSearch",
                "definition": {
                    "fields": [
                        {
                            "type": "vector",
                            "path": "embedding",
                            "numDimensions": settings.EMBEDDING_DIMENSIONS,
                            "similarity": "cosine",
                        },
                        {"type": "filter", "path": "clause_id"},
                        {"type": "filter", "path": "section"},
                        {"type": "filter", "path": "version_id"},
                    ]
                },
            }
        )
        logger.info("Created ISO vector search index", index=index_name)
    except Exception as exc:
        logger.warning("ISO vector index check/create skipped", error=str(exc))


async def seed_clauses(db: Any, version_id: str = DEFAULT_VERSION_ID) -> None:
    """Upsert all 32 ISO clauses with embeddings for the given version."""
    repo = ISOClausesRepository(db)
    texts = [f"{c['title']}\n{c['requirements']}" for c in CLAUSES]
    logger.info("Embedding ISO clauses", count=len(texts), version_id=version_id)
    embeddings = await embed_documents(texts)

    for clause, emb in zip(CLAUSES, embeddings):
        doc = {**clause, "version_id": version_id, "embedding": emb}
        await repo.upsert(doc)
        logger.info("Upserted clause", clause_id=clause["clause_id"], version_id=version_id)


async def seed_state_template(
    db: Any,
    version_id: str = DEFAULT_VERSION_ID,
    clauses: list[dict[str, Any]] | None = None,
) -> None:
    """Upsert 3 state template fields for each clause (96 total).

    ``clauses`` defaults to the built-in ``CLAUSES`` catalog; pass an explicit list
    to build a template for a different clause set (e.g. the benchmark version).
    """
    repo = ISOStateRepository(db)
    items = CLAUSES if clauses is None else clauses
    for clause in items:
        cid = clause["clause_id"]
        for field in _STATE_FIELDS:
            await repo.upsert({
                "version_id": version_id,
                "clause_id": cid,
                "field_path": f"{cid}.{field['suffix']}",
                "label": field["label"],
                "field_type": field["field_type"],
                "default": field["default"],
            })
    logger.info("State template seeded", clauses=len(items), fields_per_clause=len(_STATE_FIELDS), version_id=version_id)


async def seed_org_profile(db: Any, tenant_id: str, version_id: str = DEFAULT_VERSION_ID) -> None:
    """Upsert blank org_profile entries for the demo tenant."""
    for clause in CLAUSES:
        cid = clause["clause_id"]
        for field in _STATE_FIELDS:
            field_path = f"{cid}.{field['suffix']}"
            await db.org_profile.update_one(
                {"tenant_id": tenant_id, "version_id": version_id, "field_path": field_path},
                {"$setOnInsert": {
                    "tenant_id": tenant_id,
                    "version_id": version_id,
                    "field_path": field_path,
                    "value": field["default"],
                }},
                upsert=True,
            )
    logger.info("Org profile seeded for demo tenant", tenant_id=tenant_id, version_id=version_id)


# ---------------------------------------------------------------------------
# Benchmark version — reference clause set loaded from JSON
# ---------------------------------------------------------------------------

BENCHMARK_VERSION_ID = "iso-14001-benchmark"
BENCHMARK_VERSION_NAME = "ISO 14001 Benchmark"
_BENCHMARK_FILE = Path(__file__).parent / "data" / "benchmark_clauses.json"


def load_benchmark_clauses() -> list[dict[str, Any]]:
    """Read the benchmark clause set from disk.

    The file carries its own ``version_id`` from whichever build exported it; that
    is stripped here so the clauses always land under ``BENCHMARK_VERSION_ID``.
    """
    if not _BENCHMARK_FILE.exists():
        logger.warning("Benchmark clause file not found — skipping", path=str(_BENCHMARK_FILE))
        return []

    raw: list[dict[str, Any]] = json.loads(_BENCHMARK_FILE.read_text(encoding="utf-8"))
    return [{k: v for k, v in clause.items() if k != "version_id"} for clause in raw]


async def seed_benchmark_version(db: Any) -> None:
    """Upsert the benchmark clause set as its own published ISO version.

    Kept separate from the default seed so gap-analysis runs can be pointed at a
    fixed reference clause set. Idempotent: skips the embed step when the clauses
    are already present.
    """
    clauses = load_benchmark_clauses()
    if not clauses:
        return

    await ISOVersionsRepository(db).upsert({
        "version_id": BENCHMARK_VERSION_ID,
        "name": BENCHMARK_VERSION_NAME,
        "description": "Reference ISO 14001 clause set used as the gap-analysis benchmark",
        "status": "published",
        "source": "benchmark",
        "clause_count": len(clauses),
        "created_by": "system",
    })

    existing = await db.iso_clauses.count_documents({"version_id": BENCHMARK_VERSION_ID})
    if existing >= len(clauses):
        logger.info("Benchmark clauses already seeded — skipping embed", count=existing)
        return

    # Same embedding formula as seed_clauses / the AI build pipeline.
    texts = [f"{c.get('title', '')}\n{c.get('requirements', '')}" for c in clauses]
    logger.info("Embedding benchmark clauses", count=len(texts), version_id=BENCHMARK_VERSION_ID)
    embeddings = await embed_documents(texts)

    repo = ISOClausesRepository(db)
    for clause, emb in zip(clauses, embeddings):
        await repo.upsert({**clause, "version_id": BENCHMARK_VERSION_ID, "embedding": emb})

    await seed_state_template(db, BENCHMARK_VERSION_ID, clauses=clauses)
    logger.info("Benchmark version seeded", version_id=BENCHMARK_VERSION_ID, clauses=len(clauses))


async def _backfill_version_id(db: Any) -> None:
    """Stamp existing documents that pre-date versioning with the default version_id."""
    for collection in ("iso_clauses", "iso_state_template", "org_profile", "state_store"):
        result = await db[collection].update_many(
            {"version_id": {"$exists": False}},
            {"$set": {"version_id": DEFAULT_VERSION_ID}},
        )
        if result.modified_count:
            logger.info("Backfilled version_id", collection=collection, count=result.modified_count)


async def run_seed(demo_tenant_id: str) -> None:
    """Main entry point — idempotent."""
    db = get_database()

    # Backfill existing data that pre-dates versioning
    await _backfill_version_id(db)

    # Upsert the default version metadata
    versions_repo = ISOVersionsRepository(db)
    await versions_repo.upsert({
        "version_id": DEFAULT_VERSION_ID,
        "name": "ISO 14001:2015",
        "description": "ISO 14001:2015 Environmental Management Systems — Requirements",
        "status": "published",
        "source": "seed",
        "clause_count": len(CLAUSES),
        "created_by": "system",
    })
    logger.info("Default ISO version upserted", version_id=DEFAULT_VERSION_ID)

    # Before the early-return below — that only guards the *default* clause set,
    # so the benchmark would never seed on an already-seeded database.
    await seed_benchmark_version(db)

    existing = await db.iso_clauses.count_documents({"version_id": DEFAULT_VERSION_ID})
    if existing >= len(CLAUSES):
        logger.info("ISO clauses already seeded — skipping clause embed", count=existing)
        await ensure_iso_vector_index(db)
        return

    logger.info("Starting ISO knowledge seed", target_clauses=len(CLAUSES))
    await seed_clauses(db, DEFAULT_VERSION_ID)
    await seed_state_template(db, DEFAULT_VERSION_ID)
    await seed_org_profile(db, demo_tenant_id, DEFAULT_VERSION_ID)
    await ensure_iso_vector_index(db)
    logger.info("ISO knowledge seeding complete")
