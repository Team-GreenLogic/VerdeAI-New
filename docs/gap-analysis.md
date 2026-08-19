# Gap Analysis — Architecture & Prompts

Reference for the ISO 14001 gap-analysis subsystem: how a tenant's uploaded documents
are compared against ISO clauses to produce a compliance verdict, and the exact prompts
that drive each LLM step.

Source of truth:
- `services/gap-analyzer/app/actors.py` — orchestration
- `services/gap-analyzer/app/pipeline/analyse_clause.py` — per-clause LangGraph
- `services/gap-analyzer/app/pipeline/validation.py` — deterministic grounding + decision
- `services/gap-analyzer/app/pipeline/schemas.py` — output schemas
- `services/gap-analyzer/app/pipeline/aggregation.py` — parent-clause aggregation
- `shared/verdeai_shared/iso/slots.py` — slot schemas and the clause-state derivation
- `services/iso-knowledge/app/generate_slot_schemas.py` — build-time slot generation
- `shared/verdeai_shared/llm/prompts/*.j2` — prompt templates
- `shared/verdeai_shared/retrieval/hybrid.py` — retrieval

---

## 1. Two layers

**Orchestration** (`actors.py`) consumes `analyses.requested` from RabbitMQ, loads the
clause set for the requested ISO version, and iterates clauses one at a time. Each
clause result is persisted to `result_store` immediately, so a restarted analysis skips
already-completed clauses — the pipeline is crash-resumable by design. When all clauses
are done it publishes `analyses.gaps.ready`, which fans out to the `recommendation` and
`missing-requirements` services.

**Per-clause decision** (`analyse_clause.py`) is a 10-node LangGraph state machine,
compiled once at import and reused for every clause.

```
analyses.requested
      │
      ▼
 load clauses (iso_clauses, by version_id)
      │
      ├── for each clause ──► [ clause graph ] ──► result_store.upsert()
      │
      ▼
analyses.gaps.ready ──► recommendation
                    └─► missing-requirements
```

---

## 2. Clause pipeline

```
embed → retrieve → grade_evidence ─┬─(≥ MIN_RELEVANT_CHUNKS)→ load_org_profile → load_slot_schema
                                   │       → slot_fill → gap_analyse → verify_grounding ─┬─(grounded)→ reconcile → persist → END
                                   │                                ▲                        ├─(retries left)→ gap_analyse
                                   │                                └───repair feedback───────┘
                                   │                                                         └─(exhausted)→ insufficient_persist → END
                                   └─(too few)────────────────────────────────────────────────────────────► insufficient_persist → END
```

| Node | Prompt | Model | Output schema |
|---|---|---|---|
| `embed` | — | Voyage `voyage-3-large` (`embed_query`) | — |
| `retrieve` | — | vector + BM25 → RRF → Voyage rerank | — |
| `grade_evidence` | `evidence_grader.j2` | `GRADER_MODEL` ‖ `CHEAP_REASONING_MODEL` | `EvidenceGrade` |
| `load_org_profile` | — | Mongo query | — |
| `load_slot_schema` | — | `clause_slot_schema()` | — |
| `slot_fill` | `slot_fill_system.j2` + `slot_fill_user.j2` | `PRIMARY_REASONING_MODEL` | `SlotFillResult` |
| `gap_analyse` | `gap_analyse_system.j2` + `gap_analyse_user.j2` | `PRIMARY_REASONING_MODEL` | `GapVerdict` |
| `verify_grounding` | `groundedness_judge.j2` | `GRADER_MODEL` ‖ `CHEAP_REASONING_MODEL` | `GroundednessResult` |
| `reconcile` | — | pure functions, no LLM | — |
| `persist` / `insufficient_persist` | — | `result_store` | — |

Every LLM call goes through `verdeai_shared.llm.structured.stream_structured`, which
parses **and** validates against the Pydantic schema with a repair retry — never a bare
`json.loads`.

### Node detail

**`embed`** — builds the retrieval query via `build_query_text()`: prefers the clause's
LLM-generated `search_query` (phrased for semantic search over company documents), falling
back to `title + "\n" + requirements` for clauses predating that field. Embeds with
`input_type="query"`. The query text is threaded through state so `retrieve` reuses it.

**`retrieve`** — `hybrid_retrieve()` runs Atlas vector search and BM25 in parallel, fuses
with Reciprocal Rank Fusion (`k=60`), then reranks with Voyage. Filters by `tenant_id`
throughout — this is the multi-tenancy isolation boundary. Superseded chunks are excluded.
Returns up to `RERANK_TOP_K` chunks. Filenames are attached afterward (chunks store only
`document_id`).

**`grade_evidence`** — CRAG-style relevance filtering, two stages: drop chunks below
`RERANK_SCORE_THRESHOLD`, then an optional LLM grader narrows further. Without this the
model receives a fixed top-N regardless of quality. If the grader call fails, it degrades
to the score filter alone rather than aborting.

**`load_slot_schema`** — loads the clause's slot schema: the set of information ISO requires
for the clause to be fulfilled, one slot per required piece, each with its own extraction
question, `required` flag and fill rules (see §2.1). `clause_slot_schema()` prefers the
generated `slot_schema` on the clause document and otherwise synthesizes one from
`requirements_list`, so there is a single code path and no un-slotted clause to special-case.

**`slot_fill`** — answers each slot's extraction question from the evidence and records a
state per slot (`filled` / `partially_filled` / `not_filled` / `not_applicable`). Explicitly
*not* a compliance judgement — the prompt never mentions verdicts. Deliberately has no
try/except: an unrepairable failure propagates so the actor records an `Error` decision,
rather than silently deriving `Not Met` from an empty fill.

**`gap_analyse`** — writes up the verdict: `reasoning`, `citations`, `missing_evidence`. It
reports the decision the slot states imply rather than owning it (the derivation is applied
in `reconcile` regardless). Checks for a `paused` analysis status before running. On a
grounding-repair retry, the previous verdict and the failure reasons are appended as extra
conversation turns (see §4).

**`verify_grounding`** — the anti-hallucination core. Combines a deterministic rule check
with an LLM groundedness judge; `passed = deterministic AND judge`. If the judge call
fails it proceeds on the deterministic check alone. The "Not Met needs a material unmet
finding" rule is waived here for slot-filled clauses — materiality comes from the schema,
not from the model, so there is nothing for it to record.

**`reconcile`** — derives the final decision from slot completeness rather than trusting the
model's stated decision, replaces `findings` with the slot-derived ones, and strips citations
that failed grounding.

### 2.1 Slot schemas

Each clause carries a `slot_schema`: a company-blind description of what ISO demands. It names
no document, tenant or evidence source, is generated once per ISO version by
`services/iso-knowledge/app/generate_slot_schemas.py`, and is reused by every analysis.

```json
{
  "slot_id": "responsible_party",
  "label": "Responsible party",
  "question": "Identify the specific person, job role, department, function, or organizational unit that has been assigned responsibility for carrying out the actions needed to achieve the environmental objective.",
  "value_type": "person_or_role",
  "required": true,
  "multiple": false,
  "fill_rule": {
    "filled": "A specific person, role, department, function, or organizational unit is clearly assigned responsibility.",
    "partially_filled": "Responsibility is mentioned, but the responsible person or organizational role is vague or cannot be clearly identified.",
    "not_filled": "No responsibility assignment can be established."
  }
}
```

The `question` is the load-bearing field: a detailed instruction naming every acceptable form
of the answer, not a bare interrogative ("Who is responsible?" is the failure mode).

**Why this layer exists.** Previously the analyser was asked "does this company comply with
clause X?", and the part of that judgement which is a property of the *standard* — whether an
obligation is mandatory — was re-derived by the model on every run. It rarely committed: across
38 benchmark clauses the v4 analyser marked a finding `material: true` twice. That flag is now
`Slot.required`, fixed in data, reviewable and correctable through the admin API.

Generate with `make gen-slots` (`ARGS="--dry-run"` first — read the questions; a weak schema
degrades every analysis that follows).

---

## 3. Prompts (verbatim)

### 3.1 `evidence_grader.j2`

```jinja
You are a strict relevance grader for a compliance evidence-retrieval system (CRAG-style filtering).

You will be shown an ISO 14001 clause (with its normative requirements) and a numbered list of
retrieved document chunks. For each chunk, decide whether it is genuinely relevant to assessing
compliance with this specific clause — i.e. whether a human auditor would use it as evidence.

Rules:
- A chunk is relevant if it directly addresses the clause's subject matter (policies, procedures,
  records, roles, or facts the clause requires the organisation to have or do).
- A chunk that only mentions the topic in passing, or belongs to an unrelated clause/section, is
  NOT relevant — reject it even if it shares some vocabulary with the clause.
- Do not evaluate compliance itself here — only relevance of each chunk to the clause's subject.

Clause {{ clause_id }}: {{ clause_title }}

ISO 14001 normative requirements:
{{ clause_requirements }}

Candidate evidence chunks:
{{ evidence_chunks }}

Required output schema:
{
  "relevant_indices": [<1-based Chunk numbers judged relevant to this clause>]
}

Output ONLY valid JSON. No prose, no markdown fences.
```

### 3.1a `generate_slots_system.j2` (build time, not per analysis)

Run once per ISO version by `generate_slot_schemas.py`, never during an analysis. Abridged —
see the template for the full text, including the worked 6.2.2 example it ships.

```jinja
You are an ISO management-systems standards analyst. Your task is to convert one clause of
ISO 14001 into a slot schema: the exact set of information the standard requires to exist for
that clause to be fulfilled.

You are describing THE STANDARD, not any organisation. You have never seen a company, a
document, a management system, or any evidence, and none exists. Never mention companies,
documents, filenames, records, evidence, audits, or systems of record. [...]

"required" — true when ISO makes this information mandatory for the clause. Set false ONLY
             when the standard itself conditions the requirement ("as applicable", "where
             relevant", "if the organization chooses to"). Do not set false because the
             information seems minor or hard to obtain — materiality here is a property of
             the standard, and it is the single most consequential field in this schema.

WRITING THE "question"

A question must be a detailed instruction that names every acceptable form of the answer, so
that the reader knows exactly what counts. Never a bare interrogative.

  BAD:  "Who is responsible?"
  GOOD: "Identify the specific person, job role, department, function, or organizational
         unit that has been assigned responsibility for carrying out or achieving the
         environmental objective."
[...]
```

### 3.2 `slot_fill_system.j2`

```jinja
You are performing structured information extraction against ISO 14001 requirement slots.

You are NOT deciding whether anything is compliant. You are answering a fixed list of specific
questions from the material in front of you, and recording how completely each one could be
answered. The words "compliant", "non-compliant", "gap", "conformity", "Met" and "Not Met" have
no place in this task — something else consumes your output and makes that judgement.

Answer each slot's "question" using ONLY the organisation profile values and the retrieved
evidence chunks provided. Then apply THAT SLOT'S OWN "fill_rule" to choose its state.

Rules (non-negotiable):
- Emit exactly one entry per slot_id in the schema. No extras, no omissions, no renaming.
- The fill_rule on each slot is the authority for its state. Read it and apply it literally.
  Do not substitute your own sense of whether the answer is good enough.
- Use ONLY the provided material. Do not draw on general ISO 14001 knowledge, and do not infer
  what the organisation probably does from what similar organisations usually do.
- Absence of information is "not_filled". Silence is never evidence that something exists.
- "partially_filled" is for information that IS present but vague, generic, incomplete, or that
  cannot be pinned to a specific answer. If you cannot state the answer, it is not "filled".
- "not_applicable" ONLY when the evidence positively shows the slot's conditional trigger does
  not apply to this organisation. Never use it because the information is simply missing.
- "value" carries the extracted answer, quoted or closely paraphrased from the material — the
  actual name, date, criterion, or description you found. Leave it "" when not_filled.
- "citation_ids" are 1-based indices of the numbered evidence chunks shown to you. Cite every
  chunk you drew the answer from. Never write an index for a chunk that was not shown.
- "notes" is one short sentence, only when the state needs explaining (why partial, why
  not_applicable). Leave it "" otherwise.

Output ONLY valid JSON matching the required schema. No prose, no markdown fences.
```

### 3.3 `slot_fill_user.j2`

```jinja
Clause {{ clause_id }}: {{ clause_title }}

ISO 14001 normative requirements for this clause (context only — answer the slots, not this):
{{ clause_requirements }}

Slots to fill:
{{ slot_schema_json }}

Organisation profile values:
{{ org_profile_json }}

Retrieved evidence chunks:
{{ evidence_chunks }}

Required output schema:
{
  "slot_fills": [
    {
      "slot_id": "<must match a slot_id above>",
      "state": "filled|partially_filled|not_filled|not_applicable",
      "value": "<the extracted answer, or \"\">",
      "citation_ids": [<1-based chunk numbers>],
      "notes": "<one sentence, or \"\">"
    }
  ]
}

Produce the JSON now.
```

### 3.4 `gap_analyse_system.j2`

```jinja
You are a senior ISO 14001 lead auditor writing up a structured compliance verdict for a single
clause, on the basis of a completed slot fill.

HOW THIS CLAUSE WAS ASSESSED
The clause has been decomposed into slots: the individual pieces of information ISO requires for
this clause to be fulfilled. A prior step answered each slot's extraction question from the
evidence and recorded a state:
  "filled"           — the required information is present and specific.
  "partially_filled" — the information is present but vague, generic, or incomplete.
  "not_filled"       — nothing in the evidence establishes it.
  "not_applicable"   — the evidence shows this slot's conditional trigger does not apply.
Each slot also carries "required": whether ISO makes that information mandatory for this clause.
That flag is a property of the standard, fixed in the schema. It is not yours to re-judge.

THE DECISION IS DERIVED, NOT ARGUED
The clause decision follows arithmetically from the slot states, over the slots that are
required and not not_applicable:
  every one filled          -> "Met"
  none filled or partial    -> "Not Met"
  anything in between       -> "Partially Met"
Report the decision this rule produces. Do not reason your way to a different one — a mismatch
is corrected downstream and your reasoning is then left contradicting the recorded verdict.
"Insufficient Evidence" is not available to you here: evidence sufficiency was settled before
the slots were filled.

YOUR JOB
Explain the verdict and ground it. Specifically:
- "reasoning": walk the slots that decided the outcome. Name the slot, say what the evidence did
  or did not establish for it, and cite the chunk. Lead with the unfilled and partially filled
  required slots — those are what the reader needs. Do not restate every filled slot.
- "citations": the evidence behind that account.
- "missing_evidence": what would need to exist to fill the unfilled required slots.

CLAUSE SCOPE — NO CROSS-CLAUSE LEAKAGE
Discuss only this clause's slots. A weakness that primarily concerns another ISO requirement
does not belong in this verdict, however visible it is in the evidence. Do not convert every
operational deficiency in the documents into a gap for the clause being assessed.

ONGOING ACTIVITY vs DEMONSTRATED VIOLATION
Where a slot concerns an ongoing process — continual improvement, monitoring, review,
maintenance, continual suitability — the information ISO requires is that the process is
established and operating, not that every related activity has been completed or every target
already achieved. An open, future-dated or ongoing action does not by itself make a slot
unfilled. Equally, do not describe a slot as satisfied when the evidence shows the required
activity is actually absent, bypassed or violated. One successful instance does not establish a
requirement that applies broadly.

"missing_evidence":
- One item per unfilled or partially filled REQUIRED slot, naming the specific document type or
  data point that would fill it — never "more documentation" or "insufficient records".
- Nothing for slots that are filled, optional, or not_applicable.
- Empty list when every required slot is filled, even if improvement activities remain open.

"findings" — one entry per slot, echoing the fill:
- "req_id" MUST exactly match a slot_id from the slot fill.
- "status": "satisfied" for filled, "partial" for partially_filled, "unmet" for not_filled.
- "citation_ids": the 1-based Chunk numbers grounding that slot.
- Omit not_applicable slots.

Anti-hallucination constraints:
- Every claim in "reasoning" MUST cite a specific chunk position (Chunk N) or a slot_id.
- Only reference "Chunk N" numbers that actually appear in the "Supporting evidence chunks"
  section below — never invent a chunk number that was not shown to you.
- Do not assert information that no slot fill recorded. If a slot is not_filled, the evidence
  did not establish it; do not supply it from general ISO knowledge or from what similar
  organisations usually do.
- "citations" MUST NOT be empty. "Met" requires at least one grounded citation showing
  implementation; "Not Met" and "Partially Met" require at least one grounded citation
  evidencing the deficiency.
- Confidence must reflect evidence quality: use < 0.5 when fewer than 2 evidence chunks support
  the verdict. This cap is enforced downstream regardless of the value you supply.
- Do NOT reference ISO sub-clauses or requirements not present in the normative text provided.

FINAL CHECK
1. Count the required slots that are not not_applicable.
2. How many are filled? How many are not?
3. Apply the derivation rule above. That is your "decision".
4. Does your reasoning explain that outcome, citing chunks — rather than arguing for a
   different one?

Output ONLY valid JSON. No prose, no markdown fences, no explanation outside the JSON object.
```

### 3.5 `gap_analyse_user.j2`

```jinja
Clause {{ clause_id }}: {{ clause_title }}

ISO 14001 normative requirements:
{{ clause_requirements }}

Slot schema for this clause (what ISO requires, and whether each is mandatory):
{{ slot_schema_json }}

Slot fill (what the evidence established, from the prior extraction step):
{{ slot_fills_json }}

Supporting evidence chunks (ranked by relevance):
{{ evidence_chunks }}
{% if prior_verdict %}
Previous verdict for this clause (from an earlier analysis — may now be outdated because documents have been added, modified, or removed). Use it only as reference; RE-JUDGE strictly against the slot fill and evidence chunks shown above, which reflect the current documents:
Previous decision: {{ prior_verdict.decision }}
Previous reasoning: {{ prior_verdict.reasoning }}
{% endif %}
Required output schema:
{
  "decision": "Met|Partially Met|Not Met",
  "confidence": <0.0-1.0>,
  "reasoning": "<chain of evidence naming slot_ids and Chunk N positions>",
  "findings": [
    {
      "req_id": "<slot_id from the slot fill>",
      "status": "satisfied|partial|unmet",
      "citation_ids": [<1-based Chunk numbers grounding this slot>],
      "notes": "<one sentence>"
    }
  ],
  "citations": [
    {"type": "chunk", "chunk_id": "Chunk <N>", "page": <number>} |
    {"type": "org_profile", "field_path": "<path>"}
  ],
  "missing_evidence": ["<specific document type or named data point needed>"]
}

Produce the JSON verdict now.
```

### 3.6 `groundedness_judge.j2`

```jinja
You are an independent fact-checker reviewing a compliance verdict for faithfulness to its evidence.

You will be shown the evidence chunks that were retrieved for a clause, and the reasoning + findings
produced by a compliance-analysis model. Your job is ONLY to check whether every factual claim in
the reasoning and findings is actually supported by the evidence shown — not to re-judge compliance.

Rules:
- A claim is grounded if the cited evidence chunk(s) or organisation-profile values actually state
  or clearly imply it.
- A claim is NOT grounded if: it cites a chunk that doesn't say what's claimed, it asserts something
  no chunk addresses, or it draws a conclusion the evidence doesn't support.
- Absence of evidence for a sub-point is not itself an ungrounded claim — flag it only if the
  reasoning asserts something as fact that isn't backed by the evidence shown.
- Be strict: this check exists specifically to catch hallucination before the verdict is persisted.

Supporting evidence chunks:
{{ evidence_chunks }}

Analysis reasoning:
{{ reasoning }}

Analysis findings:
{{ findings_json }}

Required output schema:
{
  "grounded": <true|false>,
  "unsupported_claims": ["<verbatim or paraphrased claim that lacks evidentiary support>"],
  "reason": "<one sentence summary of your judgement>"
}

Output ONLY valid JSON. No prose, no markdown fences.
```

### 3.7 Repair-loop message (inline, not a template)

When `verify_grounding` fails and retries remain, `gap_analyse` is re-entered with the
previous verdict and this message appended (`analyse_clause.py`):

```
Your previous verdict failed grounding verification:
{feedback}

Revise the verdict so every citation and every 'Chunk N' mention in 'reasoning'
corresponds to a chunk actually shown in 'Supporting evidence chunks' above.
Return the corrected JSON verdict now.
```

---

## 4. Decision layer

**The LLM's `decision` is a proposal, not the verdict.**

### Deterministic grounding (`check_deterministic_grounding`)

- Citations whose `chunk_id` doesn't resolve to a retrieved chunk index are **dropped**.
- `Met` / `Not Met` / `Partially Met` with zero grounded citations → **fail**. Every decision
  asserting a compliance conclusion must point at evidence; `Insufficient Evidence` is the
  only exemption, since by definition it has nothing to cite.
- `reasoning` mentioning a `Chunk N` outside the retrieved range → **fail** (fabrication catch).
- A `Not Met` verdict carrying no `unmet` finding with `material: true` → **fail**. Waived
  (`require_material_for_not_met=False`) for slot-filled clauses, where materiality comes from
  the schema and the findings are rebuilt downstream.

Failure routes back to `gap_analyse` with feedback, up to `MAX_VERIFY_RETRIES`; after that
the verdict is abandoned in favour of Insufficient Evidence rather than persisted.

### Decision derivation (`score_clause` → `reconcile_decision`)

The decision follows arithmetically from **weighted slot coverage**, over the slots that are
`required` and not `not_applicable`:

```
credit   = {filled: 1.0, partially_filled: 0.5, not_filled: 0.0}
coverage = Σ(weight × credit) / Σ(weight)

1. any `critical` slot contradicted by evidence → Not Met   (gate, overrides the bands)
2. coverage ≥ 0.85                              → Met
3. coverage ≥ 0.15                              → Partially Met
4. otherwise                                    → Not Met
```

**Why coverage rather than a conjunctive rule.** The previous rule required *every* required
slot filled for `Met` and *zero* filled for `Not Met`. Measured slot marginals are
`filled 52%`, `partially_filled 34%`, `not_filled 14%`, and clauses average 5.2 required slots —
so `P(Met) ≈ 0.52^5 ≈ 4%` and `P(Not Met) ≈ 0.14^5 ≈ 0.006%`. Both classes were structurally
unreachable and everything collapsed into `Partially Met`; the observed run matched the
prediction (Met 5, Partially Met 26, Not Met 0). Decision class tracked *slot count*, not
compliance — the clauses that reached `Met` were the two- and three-slot ones. Half-credit for
`partially_filled` is what makes the result continuous: a third of all real answers are partial,
and a conjunctive rule discards that information entirely.

**Why `Not Met` is a gate, not a low band.** Benchmark clause 6.1.2 is gold `Not Met` at
coverage 0.79 — five of six required slots satisfied, but the one carrying the clause's core
determination contradicted by an audit nonconformity. Averaging buries that. Conversely 7.4.2
has an unfilled required slot and is gold `Partially Met`, because its gold reason reads
"limited evidence that…" — absence of proof, not proof of absence. So the gate fires only on
`critical` **and** `contradicted`, never on a slot that is merely empty. This mirrors the
benchmark's own rubric, which states `NOT_MET` is "not used merely because a document is absent".

`weight` and `critical` are slot properties in `benchmark_slot_schemas.json`, authored from the
ISO text; 66 of 184 slots are critical. Neither is an LLM judgement.

A slot the fill step failed to report counts as `not_filled` — silence about a requirement is
not evidence that it is satisfied. A clause whose required slots are all `not_applicable` falls
back to its optional slots, and degrades to `Partially Met` rather than `Not Met` when none
carries information: every obligation there is one the standard itself conditions, so asserting
nonconformity would be a claim the evidence does not support. `Insufficient Evidence` is not
reachable here — evidence sufficiency is settled upstream by `_route_after_grade`.

The full derivation is persisted on the result as `decision_trace` (a `ClauseScore`): coverage,
the band applied, the credit breakdown per slot, and any critical failures. The verdict can
therefore be re-checked against its own arithmetic rather than against the prose the model wrote
beside it — which has, in practice, disagreed with the recorded decision.

`reconcile_decision` takes this as `derived_override`. Without one it falls back to deriving
from the findings themselves (`any unmet + material → Not Met`; `all satisfied → Met`; else
`Partially Met`) — the path clauses assessed before the slot layer still take.

Findings are then rebuilt from the slots: `filled → satisfied`, `partially_filled → partial`,
`not_filled → unmet`, with `material` taken from the slot's `required` flag and
`not_applicable` slots emitting no finding at all. So `material` is now a property of the
standard rather than something the model volunteers per run — see §2.1 for why that changed.

### Parent-clause aggregation (`pipeline/aggregation.py`)

Clauses are analysed independently, so a parent can be scored more leniently than its own
children. After every verdict is persisted — and before `gap_count` is finalised or
`analyses.gaps.ready` is published — `aggregate_parent_decisions` overwrites each parent from
its children, worst-child-wins:

```
any child Not Met               → parent Not Met
else any Insufficient Evidence  → parent Insufficient Evidence
else any Partially Met          → parent Partially Met
else                            → parent Met
```

Parents are resolved deepest-first so multi-level hierarchies compose. Unrecognised decisions
(e.g. `Error`) count as Insufficient Evidence — never as Met. It runs over the full result set,
so delta re-runs also re-derive parents that were copied forward rather than re-analysed.

If the derived decision disagrees with the LLM's, **the derived decision wins**, confidence
is capped at 0.5, and a `[Reconciliation note: ...]` is appended to the reasoning.

Confidence is separately clamped to ≤ 0.5 when fewer than 2 grounded chunks support the verdict.

### Evidence sufficiency and abstain paths

Every result carries `evidence_status`:

| value | meaning |
|---|---|
| `sufficient` | enough graded evidence survived to judge normally |
| `degraded` | too little survived the relevance filters, so the clause was judged on the top `MIN_RELEVANT_CHUNKS` chunks by rerank score and the verdict is flagged as weakly supported |
| `none_retrieved` | retrieval returned nothing at all |

The `degraded` path exists because abstaining was measurably worse than answering weakly: on the
five-company benchmark, 7 of 38 clauses returned `Insufficient Evidence` — including 8.2 and 9.3,
while the tenant's own corpus held `Emergency_Response_Plan` and `Management_Review_Minutes`.
Gold assigned `Insufficient Evidence` to none of them, so each abstention was an outright error
worth ~18 accuracy points between them. An absolute rerank-score floor is not a reliable signal
that evidence is unusable.

Two paths still persist the fixed `_INSUFFICIENT` result rather than a fabricated verdict:

1. Nothing was retrieved at all — there is genuinely nothing to judge.
2. The verdict could not be grounded within the retry budget.

Failures inside `slot_fill` / `gap_analyse` deliberately **propagate** — the actor records an
`Error` decision instead of degrading to a plausible-looking Insufficient Evidence. For
`slot_fill` this matters twice over: an empty fill would derive `Not Met` for the whole clause.

---

## 5. Configuration

| Setting | Default | Effect |
|---|---|---|
| `RETRIEVAL_TOP_K` | 30 | candidates fetched per retriever before fusion |
| `RERANK_TOP_K` | 8 | chunks surviving rerank |
| `RERANK_SCORE_THRESHOLD` | 0.3 | rerank floor applied before grading |
| `MIN_RELEVANT_CHUNKS` | 2 | below this → abstain, no LLM verdict |
| `MAX_VERIFY_RETRIES` | 2 | grounding repair-loop bound |
| `EVIDENCE_GRADER_ENABLED` | true | toggles the LLM relevance pass |
| `GRADER_MODEL` | `""` | blank → falls back to `CHEAP_REASONING_MODEL` |
| `EMBEDDING_DIMENSIONS` | 1024 | Voyage `voyage-3-large` |

Model IDs resolve from `.env`, which is **not committed** — the defaults in `settings.py`
(`deepseek/deepseek-r1-0528`, `qwen/qwen3-coder`) are not what a given deployment actually
runs. Record the resolved `PRIMARY_REASONING_MODEL`, `CHEAP_REASONING_MODEL` and
`GRADER_MODEL` alongside any benchmark results; they are the largest uncontrolled variable
between runs.

---

## 6. Delta re-analysis

A re-run in `mode="delta"` avoids re-analysing every clause. `_compute_affected_clauses`
determines which clauses a document change actually invalidates, using chunk supersession
(`superseded` / `superseded_at`) against the parent analysis baseline, plus the
`source_document_ids` stamped on each stored verdict at persist time. Unaffected clauses
have their verdicts — and their downstream recommendations and missing-requests — copied
forward. Affected clauses are re-run with their previous verdict supplied as
`prior_verdict` (see `gap_analyse_user.j2`), explicitly instructed to re-judge against
current evidence rather than defer to it.

Preparation is idempotent, gated by a `delta_prepared` sentinel, so a redelivered message
does not duplicate work.

---

## 7. Known gaps

- **No accuracy benchmark in the repo.** `tests/eval/golden_set.json` is a 9-row placeholder
  that contradicts the gold labels used in development, so prompt, retrieval and threshold
  changes cannot be scored — only inspected. The pure functions in `validation.py` and
  `verdeai_shared/iso/slots.py` have no I/O and are directly unit-testable against labeled
  cases; that is the cheapest place to start.
- **Slot schemas are LLM-generated and unreviewed at scale.** `required` now decides clause
  outcomes, so a wrong flag is a silent, systematic scoring error across every analysis of that
  version. `--dry-run` and the admin API exist for exactly this; nobody has walked all 38.
- **No clause cross-reference structure.** ISO 14001 clauses reference each other
  extensively ("the issues referred to in 4.1", "see 9.1, 9.2 and 9.3") and those references
  sit unused in the `requirements` text.
- **Deontic modality is only implicit.** `shall` / `should` / `may` are not distinguished in
  the `requirements` prose; the slot schema's `required` flag is now the only place the
  distinction is recorded, and it is inferred by the generating model rather than parsed.
- **`keywords`** is generated per clause but consumed nowhere.
