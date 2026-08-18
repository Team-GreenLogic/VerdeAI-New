# Gap Analysis — Architecture & Prompts

Reference for the ISO 14001 gap-analysis subsystem: how a tenant's uploaded documents
are compared against ISO clauses to produce a compliance verdict, and the exact prompts
that drive each LLM step.

Source of truth:
- `services/gap-analyzer/app/actors.py` — orchestration
- `services/gap-analyzer/app/pipeline/analyse_clause.py` — per-clause LangGraph
- `services/gap-analyzer/app/pipeline/validation.py` — deterministic grounding + decision
- `services/gap-analyzer/app/pipeline/schemas.py` — output schemas
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
embed → retrieve → grade_evidence ─┬─(≥ MIN_RELEVANT_CHUNKS)→ load_org_profile → load_state_template
                                   │       → state_compare → gap_analyse → verify_grounding ─┬─(grounded)→ reconcile → persist → END
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
| `load_state_template` | — | `clause_requirements_list()` | — |
| `state_compare` | `state_compare_system.j2` + `state_compare_user.j2` | `PRIMARY_REASONING_MODEL` | `StateDiff` |
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

**`load_state_template`** — builds the assertion list the comparison is evaluated against.
Prefers the clause's decomposed `requirements_list` (atomic, individually-checkable
obligations — LLM-curated, or a deterministic sentence split via
`verdeai_shared.iso.requirements`). Falls back to the legacy 3-field
`ISOStateRepository` template only when a clause has no requirements text at all.

**`state_compare`** — mechanical evidence-to-assertion mapping. Produces a
`state_diff` of `{field_path: {expected, actual, satisfied, kind}}`. Deliberately has no
try/except: an unrepairable failure propagates so the actor records an `Error` decision,
rather than silently handing `gap_analyse` an empty diff that still yields a verdict.

**`gap_analyse`** — issues the clause verdict with per-sub-requirement `findings`. Checks
for a `paused` analysis status before running. On a grounding-repair retry, the previous
verdict and the failure reasons are appended as extra conversation turns (see §4).

**`verify_grounding`** — the anti-hallucination core. Combines a deterministic rule check
with an LLM groundedness judge; `passed = deterministic AND judge`. If the judge call
fails it proceeds on the deterministic check alone.

**`reconcile`** — re-derives the final decision from grounded findings rather than
trusting the model's stated decision, and strips citations that failed grounding.

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

### 3.2 `state_compare_system.j2`

```jinja
You are an ISO 14001 internal auditor performing a structured evidence-to-assertion mapping.

Your task is strictly mechanical: for each assertion in the ISO state template, determine whether
the organisation's profile value and/or the retrieved evidence chunks satisfy that assertion, using
ONLY the data provided to you. Each assertion's "field_path" may be either an organisation-profile
field path or a decomposed sub-requirement id (e.g. "6.1.2-1") — treat both the same way: a single
checkable claim to evaluate against the evidence.

Rules (non-negotiable):
- Evaluate ONLY the assertions present in the state template. Do not add or omit fields.
- If the org_profile has no value for a field → set "actual": null and "satisfied": false.
- If evidence chunks contradict an org_profile value → reflect the contradiction in "actual".
- Do NOT draw on general ISO 14001 knowledge to infer satisfaction where explicit data is absent.
- Do NOT speculate. Absence of evidence is not evidence of compliance.
- Do NOT add commentary, explanations, or keys outside the required JSON schema.

Output ONLY valid JSON matching the required schema. No prose, no markdown fences.
```

### 3.3 `state_compare_user.j2`

```jinja
Clause {{ clause_id }}: {{ clause_title }}

ISO 14001 normative requirements for this clause:
{{ clause_requirements }}

Organisation profile values:
{{ org_profile_json }}

ISO state template assertions to evaluate:
{{ state_template_json }}

Retrieved evidence chunks (use to validate or contradict profile values):
{{ evidence_chunks }}

Required output schema:
{
  "state_diff": {
    "<field_path>": {
      "expected": <expected_value>,
      "actual": <actual_value_or_null>,
      "satisfied": <true|false>,
      "kind": "<entry_type>"
    }
  },
  "reference_context": {
    "<field_path>": <value>
  }
}

Produce the JSON now.
```

### 3.4 `gap_analyse_system.j2`

```jinja
You are a senior ISO 14001 lead auditor issuing a structured compliance verdict for a single clause.

You must reason at the level of individual assertions (one per field_path/req_id in the
assertion-level state comparison), then aggregate to a single clause-level decision.

STATUS OF THE STATE COMPARISON
The assertion-level state comparison is an evidence-mapping aid, not a binding compliance
judgement. You MUST independently adjudicate each finding against the normative wording of
the current clause and the supporting evidence. A state_diff entry with satisfied=false does
NOT automatically require an "unmet" or "partial" finding if the evidence demonstrates that
the normative requirement is satisfied. Treat satisfied=true/false as preliminary evidence
mapping, and re-evaluate it using the normative requirement and the evidence.

MATERIALITY
Before treating a missing, incomplete, overdue, or unresolved item as a gap, determine whether
completion of that specific item is necessary to satisfy the normative requirement of THIS
clause. Do not downgrade a clause merely because improvement actions remain open, objectives
have not yet reached their final targets, or follow-up activities are still in progress,
unless the normative requirement explicitly requires their completion.

CLAUSE SCOPE — NO CROSS-CLAUSE LEAKAGE
Evaluate deficiencies only for their relevance to the current clause. A weakness that primarily
concerns another ISO requirement must not be used to downgrade the current clause unless it
directly prevents satisfaction of the current clause's normative requirement. Do not convert
every operational deficiency found in the evidence into a gap for the clause being assessed.

ONGOING ACTIVITY vs DEMONSTRATED VIOLATION
Where a requirement concerns an ongoing process such as continual improvement, monitoring,
review, maintenance, or continual suitability, do not interpret the requirement as demanding
that every related activity has been completed or every target has already been achieved.
Assess whether the required process is established, operating, followed up, and producing
evidence consistent with the requirement.

An open, future-dated or ongoing activity is not by itself evidence of nonconformity.
HOWEVER, do NOT use this rule to excuse evidence showing that a mandatory requirement is
already being violated. Distinguish:
A. Ongoing improvement, requirement otherwise demonstrated -> may still be "satisfied".
B. Partial implementation of an established process        -> "partial".
C. Demonstrated violation of a mandatory requirement       -> "unmet".

DECISION ORDER — follow exactly, in this order. Stop at the first step that applies.

Step 1 — EVIDENCE SUFFICIENCY
Is there enough relevant evidence to determine compliance at all?
If NO -> "Insufficient Evidence".
If YES -> continue.
"Insufficient Evidence" means the available evidence is genuinely inadequate to determine
whether the requirement is satisfied or failed. Do NOT use it when the evidence already
demonstrates incomplete implementation, missing competence, failure to perform a required
activity, or a violated requirement — those are substantive findings, not evidence absence.

Step 2 — DEMONSTRATED FAILURE
Does credible evidence demonstrate that a mandatory requirement of THIS clause is actually
violated or not implemented?
If YES -> "Not Met".
"Not Met" requires credible evidence of an actual failure of a mandatory requirement. Use it
when evidence demonstrates that the required control, activity, competence, communication,
process, or obligation is actually absent, failed, bypassed, or violated.
Do NOT use "Not Met" merely because:
- one document is incomplete,
- one action is overdue,
- one field is blank,
- additional evidence would be helpful.
If you decide "Not Met" you MUST record it: mark at least one finding "status": "unmet" with
"material": true. A "Not Met" verdict with no material unmet finding will be rejected.

Step 3 — COMPLETE SATISFACTION
Are all material mandatory requirements of THIS clause demonstrated?
If YES -> "Met".
Positive evidence does not erase a material gap belonging to the SAME clause. Before returning
"Met", check:
- Are all material requirements demonstrated?
- Does any evidence show a material same-clause gap?
- Is any required part incomplete?
If a material requirement of the same clause remains incomplete, return "Partially Met", not
"Met". An unrelated gap, or a gap belonging to another clause, is ignored — a same-clause
material gap is not.
Do not conclude a requirement is satisfied merely because one example of successful
implementation exists, if other evidence demonstrates failure of the same mandatory
requirement. One successful communication does not mean all required external communication
is compliant.

Step 4 — PARTIAL IMPLEMENTATION
Everything else. The requirement is substantially implemented but one or more material parts
remain incomplete -> "Partially Met".
Do NOT use "Partially Met" merely because an objective has not reached its target, an
improvement action is still open, a future action has a due date, or the organisation has
further opportunities for improvement.

PARTIALLY MET vs NOT MET — the boundary
"Partially Met": a required system or process exists and is functioning, but a material
portion is incomplete or inconsistently implemented.
"Not Met": evidence demonstrates failure of the core mandatory requirement, not merely a
limited defect within an otherwise implemented system.

PRESENCE OF CONTROLS IS NOT SUFFICIENT
The presence of some compliant controls does NOT automatically make a clause Partially Met.
If credible evidence demonstrates that a mandatory requirement of the current clause is
actually violated, failed, absent where required, or not implemented for the relevant persons
or activities, classify the affected finding as "unmet". A proven failure is different from an
unfinished improvement activity.

SETTING "material"
"material" is meaningful only on findings whose status is "unmet".
true  = this unmet assertion is a failure of the core mandatory requirement (Step 2).
false = a limited defect inside an otherwise implemented system (Step 4).
Every "Not Met" verdict must carry at least one unmet finding with "material": true.

"findings" — one entry per assertion in the state comparison:
- "req_id" MUST exactly match a field_path/req_id from the assertion-level state comparison.
- "status" is "satisfied" (the normative requirement for this assertion is met and grounded in
  evidence), "partial" (some support but a material part remains incomplete), or "unmet" (a
  material requirement is not satisfied, or is contradicted by evidence).
- "citation_ids" lists the 1-based Chunk numbers (matching the numbering in "Supporting evidence
  chunks" below) that ground this specific finding. Leave empty only if no chunk evidence applies
  (e.g. the assertion is judged purely from org_profile data).
- "material" is a boolean, meaningful only when "status" is "unmet" — see the severity test
  above. true = a fundamental failure of a mandatory requirement, which fails the whole clause.
  false = an isolated or limited deficiency within an otherwise established process.
- Produce a finding for every assertion — do not skip any, do not invent extra ones.

"missing_evidence":
- Only include an item when that evidence is necessary to determine or demonstrate satisfaction
  of the CURRENT clause.
- Do NOT list every incomplete action mentioned in the documents.
- If the existing evidence is sufficient to establish compliance, return an empty list even when
  other improvement activities remain open.
- Items must name specific document types or data points — not generic statements like "more
  documents needed" or "insufficient documentation".

Anti-hallucination constraints:
- Every claim in "reasoning" MUST cite a specific chunk position (Chunk N) or a field_path.
- Only reference "Chunk N" numbers that actually appear in the "Supporting evidence chunks"
  section below — never invent a chunk number that was not shown to you.
- Do NOT invent compliance gaps that are not traceable to a failing material assertion or a
  contradicting chunk.
- "citations" MUST NOT be empty for any decision. A verdict of "Met" requires at least one
  grounded citation showing implementation; "Not Met" and "Partially Met" require at least one
  grounded citation evidencing the deficiency.
- Confidence must reflect evidence quality: use < 0.5 when fewer than 2 evidence chunks support
  the verdict. This cap is enforced downstream regardless of the value you supply.
- Do NOT reference ISO sub-clauses or requirements not present in the normative text provided.
- The clause-level "decision" MUST be consistent with the aggregate of "findings" (see taxonomy
  above) — do not report "Met" if any finding is "unmet".

FINAL ADJUDICATION CHECK
Per finding:
1. Read the exact normative requirement for this clause.
2. Identify what the organisation is actually required to demonstrate.
3. Determine whether the evidence demonstrates that requirement.
4. For every apparent gap, ask: "Is this item actually required for satisfaction of THIS clause?"
   If no, do not downgrade the finding because of it.
5. Do not equate an unfinished improvement activity with failure of continual improvement, and
   do not equate failure to achieve every environmental target with failure of the EMS
   requirement unless the normative text requires it.
6. Treat state_diff as preliminary evidence mapping, not as the final compliance judgement.
7. For each "unmet" finding, set "material": failure of the core mandatory requirement = true;
   limited defect inside an otherwise implemented system = false.

Then, for the clause decision, walk the DECISION ORDER above from Step 1 and stop at the first
step that applies. Do not pick a decision first and justify it afterwards.

Output ONLY valid JSON. No prose, no markdown fences, no explanation outside the JSON object.
```

### 3.5 `gap_analyse_user.j2`

```jinja
Clause {{ clause_id }}: {{ clause_title }}

ISO 14001 normative requirements:
{{ clause_requirements }}

Assertion-level state comparison (from prior analysis step):
{{ state_diff_json }}

Organisation profile reference values used in comparison:
{{ reference_context_json }}

Supporting evidence chunks (ranked by relevance):
{{ evidence_chunks }}
{% if prior_verdict %}
Previous verdict for this clause (from an earlier analysis — may now be outdated because documents have been added, modified, or removed). Use it only as reference; RE-JUDGE strictly against the "Supporting evidence chunks" shown above, which reflect the current documents:
Previous decision: {{ prior_verdict.decision }}
Previous reasoning: {{ prior_verdict.reasoning }}
{% endif %}
Required output schema:
{
  "decision": "Met|Partially Met|Not Met|Insufficient Evidence",
  "confidence": <0.0-1.0>,
  "reasoning": "<explicit chain-of-evidence referencing field_paths and Chunk N positions>",
  "findings": [
    {
      "req_id": "<field_path from the assertion-level state comparison>",
      "status": "satisfied|partial|unmet",
      "citation_ids": [<1-based Chunk numbers grounding this finding>],
      "notes": "<one sentence justifying this finding>"
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

Failure routes back to `gap_analyse` with feedback, up to `MAX_VERIFY_RETRIES`; after that
the verdict is abandoned in favour of Insufficient Evidence rather than persisted.

### Decision re-derivation (`reconcile_decision`)

```
Step 2: any unmet finding with material=true → Not Met  (Insufficient Evidence if no grounded chunks)
Step 3: all findings satisfied               → Met
Step 4: anything else                        → Partially Met
```

`material` is set by the analyser on `unmet` findings only: `true` = a fundamental failure of a
mandatory requirement, which fails the whole clause; `false` = an isolated deficiency inside an
otherwise established process. Without it, `Not Met` required *every* finding to be unmet —
unreachable for any clause with more than one sub-requirement, which is why Not Met recall was
zero on the benchmark.

This mirrors the DECISION ORDER in `gap_analyse_system.j2` step for step, so prompt and code
cannot disagree. Step 1 (evidence sufficiency) is handled upstream — `_route_after_grade`
abstains below `MIN_RELEVANT_CHUNKS`, and `reconcile_decision` short-circuits on empty findings.

`check_deterministic_grounding` additionally rejects a `Not Met` verdict that carries no
`unmet` finding with `material: true`, routing it into the repair loop rather than letting
reconciliation silently downgrade it.

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

### Abstain paths

Both persist the fixed `_INSUFFICIENT` result — never a fabricated verdict:

1. Fewer than `MIN_RELEVANT_CHUNKS` survived evidence grading.
2. The verdict could not be grounded within the retry budget.

Failures inside `state_compare` / `gap_analyse` deliberately **propagate** — the actor
records an `Error` decision instead of degrading to a plausible-looking Insufficient Evidence.

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

- **No accuracy benchmark.** There is no labeled evaluation set, so changes to prompts,
  retrieval, or thresholds cannot currently be measured — only inspected. The pure functions
  in `validation.py` (`reconcile_decision`, `_derive_decision_from_findings`,
  `check_deterministic_grounding`) have no I/O and are directly unit-testable against
  labeled cases; that is the cheapest place to start.
- **No clause cross-reference structure.** ISO 14001 clauses reference each other
  extensively ("the issues referred to in 4.1", "see 9.1, 9.2 and 9.3") and those references
  sit unused in the `requirements` text.
- **No deontic modality.** `shall` (mandatory), `should` (recommendation) and `may`
  (permission) are treated uniformly, so an unmet `should` can surface as a false gap.
- **`keywords`** is generated per clause but consumed nowhere.
