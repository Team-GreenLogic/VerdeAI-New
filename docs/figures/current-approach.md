# VerdeAI gap-analysis — current flow, and what changed from the old approach

## Current flow (per clause)

Ingestion (dedup → LlamaParse → Docling chunk → vision caption → Voyage embed → Mongo
Atlas index) is unchanged and not discussed here — this covers only the per-clause
LangGraph in `analyse_clause.py`, a 10-node graph run once per ISO clause:

1. **embed** — embed the clause's `search_query`.
2. **retrieve** — hybrid (vector + BM25) search over the tenant's indexed chunks.
3. **grade_evidence** — an LLM grader keeps only relevant chunks, with a relative floor:
   if fewer than `MIN_RELEVANT_CHUNKS` survive but chunks were retrieved at all, the
   top-ranked few are kept anyway and the clause is marked `evidence_status: degraded`
   rather than abstaining outright. If nothing was retrieved, `none_retrieved`. This
   replaced a bug where `if grade.relevant_indices:` conflated "grader rejected
   everything" with "grader endorsed nothing", making a total rejection *more*
   permissive than endorsing exactly one chunk.
4. **load_profile** — load the tenant's org-profile field values.
5. **load_template** → `clause_slot_schema(clause)` — load the clause's `slot_schema`
   (see below).
6. **slot_fill** (LLM, step name kept as `state_compare` internally for now) — answer
   each slot's fixed extraction question from the evidence, per that slot's own
   `fill_rule`. Explicitly barred from compliance language.
7. **gap_analyse** (LLM) — writes the narrative, citations, and `missing_evidence`. Its
   own stated `decision` is advisory; reconciliation overrides it below.
8. **verify_grounding** — deterministic checks (every citation and every "Chunk N"
   mention must resolve to an actually-retrieved chunk) plus an LLM groundedness judge.
   Ungrounded → loop back to `gap_analyse` with feedback (bounded retries), then exhaust
   to `insufficient_persist`.
9. **reconcile** — `score_clause(schema, fills)` computes the decision arithmetically;
   if it disagrees with the LLM's stated decision, the derived one wins and confidence
   is capped. Findings are replaced by the slot-derived ones (`material` = the slot's
   `required` flag, not an LLM judgement). The full derivation (`ClauseScore`) is stored
   as `decision_trace` on the result.
10. **persist** — write to `result_store`; crash-resumable (already-persisted clauses
    are skipped on restart).

After every clause in the run is done, an unconditional post-pass
(`aggregation.aggregate_parent_decisions`) derives each parent clause's decision from
its children — worst-child-wins, deepest first — and, for **title-only** clauses (ISO
14001's 6.1, 6.2, 7.4, 7.5, 9.1, 9.2 — headings with no normative "shall" text of their
own), pools their children's real slot fills into the parent's display detail
(`aggregate_children_slots`). Title-only clauses carry no `slot_schema`, get zero
retrieval and zero LLM calls, and their entire result comes from this step.

### `score_clause` — the decision arithmetic

- Coverage runs over *applicable required* slots only (`required=true` and not
  `not_applicable`), so a conditional "as appropriate" obligation that doesn't trigger
  can't drag the clause down.
- `filled` = 1.0 credit, `partially_filled` = 0.5, `not_filled` = 0.0, weighted by each
  slot's `weight`.
- coverage ≥ 0.85 → **Met**; coverage ≥ 0.15 → **Partially Met**; below → **Not Met**
  (thresholds fitted on one benchmark company, held out on four others).
- Exception that overrides the thresholds: a `critical` slot the evidence *contradicts*
  (not just missing — an audit nonconformity, a regulator finding, an empty register)
  forces **Not Met** regardless of coverage elsewhere. This is the only way a clause
  with mostly-satisfied siblings can still fail outright (benchmark clause 6.1.2: gold
  Not Met at 0.79 coverage, because one core determination failed).

## What changed vs. the old approach (`state_compare`)

The old per-clause pipeline had the same shape — `embed → retrieve → grade_evidence →
load_org_profile → load_state_template → state_compare → gap_analyse →
verify_grounding → reconcile → persist` — and the same node *names* even (git history:
`load_slot_schema` was `load_state_template`, `slot_fill` was `state_compare`). The
difference is what those two middle nodes actually did.

**Old `state_compare`** (LLM, prompt now deleted but recovered from history): given an
"ISO state template" — a flat list of assertions, each either an org-profile field path
or a decomposed sub-requirement id — the model filled in `{expected, actual, satisfied,
kind}` per assertion (`StateDiffEntry`, in a `StateDiff` schema). No `fill_rule` per
assertion, no `required`/`critical`/`weight`, no `contradicted` flag, no fixed
value-type. **`gap_analyse`** then read that `state_diff` plus a `reference_context`
blob and decided `Met`/`Partially Met`/`Not Met` mostly on its own judgement of what the
diff meant. **`reconcile`** only ever second-guessed the LLM using
`_derive_decision_from_findings` — itself just a 3-step rule over the LLM's *own*
findings (`material=true` + `status=unmet` → Not Met; all satisfied → Met; else
Partially Met) — so reconciliation could catch the model contradicting its own findings,
but had no independent signal to check the findings *against*. What counted as "enough"
to satisfy a clause, and whether an obligation was mandatory at all, was re-decided by
the model on every run.

**New `slot_fill`**: the clause's `slot_schema` is generated once per ISO version,
offline, company-blind (`generate_slot_schemas.py`) — not derived per-tenant per-run.
Each `Slot` carries its own `fill_rule` (three discriminating conditions written in
terms of the *information*, never in terms of compliance), a `value_type`, `required`,
`weight`, and `critical`. The LLM's only job is to answer the slot's question and apply
that literal rule — the system prompt explicitly forbids the words
compliant/non-compliant/gap/conformity/Met/Not Met at this step. **`reconcile`** now
calls `score_clause` — a pure function, no LLM — and that derived decision *overrides*
gap_analyse's stated decision whenever they disagree (with confidence capped), rather
than only checking the LLM's findings for self-consistency. `gap_analyse`'s job shrank
to producing narrative, citations, and missing-evidence text; it no longer effectively
picks the verdict.

Concretely, that changes:

- **What "mandatory" means** — a data property (`Slot.required`, fixed at schema-authoring
  time) instead of an LLM inference re-made every analysis.
- **How partial credit works** — old: the model's free-text judgement of the whole diff.
  New: numeric, weighted, thresholded, and auditable — every clause's `decision_trace`
  shows exactly which slots contributed what.
- **How "Not Met" is reached** — old: any `material` unmet finding, where materiality
  was itself an LLM call. New: either coverage falls below 0.15, or a `critical` slot is
  positively contradicted — a mechanism the old per-finding rule couldn't express
  (failing on one core determination while every sibling assertion passes).
- **Parent-clause aggregation** — the old pipeline analysed every clause independently,
  including heading clauses with no normative text of their own, which produced parents
  scored more leniently than their own children (gold 7.4.3 = Not Met should force
  7.4 = Not Met, but the old analyser could independently return Partially Met for 7.4).
  The new pipeline never independently analyses title-only clauses at all, and derives
  every parent's decision from its children deterministically
  (`aggregate_parent_decisions`, worst-child-wins) as an unconditional post-pass, not an
  LLM inference about hierarchy.
- **Reproducibility** — same evidence, same clause, re-run twice: old path could return
  different decisions across runs because the compliance judgement lived inside LLM
  temperature-sensitive reasoning at two separate steps (state_compare *and*
  gap_analyse). New path has exactly one place non-determinism can flip the decision
  (`slot_fill`'s per-slot state), and even there `score_clause`'s thresholds absorb small
  disagreements — flipping the overall decision now requires flipping enough slots to
  cross a coverage band, not just one LLM's overall impression.

Everything else — ingestion, hybrid retrieve, rerank, the grounding/citation checks, the
bounded repair loop on ungrounded verdicts, crash-resumability via `result_store` — is
unchanged between the two approaches.

Source: `services/gap-analyzer/app/pipeline/analyse_clause.py`,
`shared/verdeai_shared/iso/slots.py`,
`services/gap-analyzer/app/pipeline/aggregation.py`,
`services/gap-analyzer/app/pipeline/validation.py`,
`services/gap-analyzer/app/pipeline/schemas.py`,
`services/gap-analyzer/app/actors.py`,
`services/iso-knowledge/app/generate_slot_schemas.py`.
