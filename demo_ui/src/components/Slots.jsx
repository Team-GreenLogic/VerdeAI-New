import { useState } from 'react'

/**
 * Requirement slots — the ISO representation the gap analyser now runs on.
 *
 * A clause's `slot_schema` lists the pieces of information ISO requires, each with the
 * extraction question that finds it and whether the standard makes it mandatory. An
 * analysis produces one `slot_fill` per slot saying how completely the evidence answered
 * it, and the clause decision is derived from those states rather than judged by the model.
 *
 * `SlotSchemaList` shows the empty schema (admin / ISO version pages).
 * `SlotFillList`   shows a filled one (analysis results).
 */

const STATE_STYLES = {
  filled:           { chip: 'bg-emerald-100 text-emerald-700', dot: 'bg-emerald-500', label: 'Filled' },
  partially_filled: { chip: 'bg-amber-100 text-amber-700',     dot: 'bg-amber-500',   label: 'Partial' },
  not_filled:       { chip: 'bg-red-100 text-red-700',         dot: 'bg-red-500',     label: 'Not filled' },
  not_applicable:   { chip: 'bg-slate-100 text-slate-500',     dot: 'bg-slate-400',   label: 'N/A' },
}

const VALUE_TYPE_LABELS = {
  text: 'text',
  person_or_role: 'person / role',
  date_or_period: 'date / period',
  quantity: 'quantity',
  document_reference: 'document reference',
  process_description: 'process',
  criteria: 'criteria',
  list_of_items: 'list',
  boolean: 'yes / no',
}

function SlotState({ state }) {
  const s = STATE_STYLES[state] || STATE_STYLES.not_filled
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-medium flex-shrink-0 ${s.chip}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  )
}

function RequiredTag({ required }) {
  return required ? (
    <span className="text-[10px] font-semibold text-red-600 bg-red-50 rounded px-1.5 py-0.5 flex-shrink-0">
      required
    </span>
  ) : (
    <span className="text-[10px] text-slate-400 bg-slate-100 rounded px-1.5 py-0.5 flex-shrink-0">
      conditional
    </span>
  )
}

/** Count line shared by both views. */
export function SlotSummary({ slots = [] }) {
  const required = slots.filter(s => s.required).length
  if (!slots.length) return null
  return (
    <span className="text-[11px] text-slate-400">
      {slots.length} slot{slots.length === 1 ? '' : 's'}
      {required > 0 && <> · <span className="text-red-500 font-medium">{required} required</span></>}
    </span>
  )
}

/**
 * The decision arithmetic, shown as a bar.
 *
 * `trace` is the `decision_trace` persisted with the result: coverage over applicable required
 * slots, the band that was applied, and any critical slot whose failure overrode the band.
 * Showing it means the verdict can be checked against its own derivation.
 */
export function CoverageBar({ trace }) {
  if (!trace || typeof trace.coverage !== 'number') return null
  const pct = Math.round(trace.coverage * 100)
  const gated = (trace.critical_failures || []).length > 0
  const tone = gated
    ? 'bg-red-500'
    : trace.decision === 'Met' ? 'bg-emerald-500'
    : trace.decision === 'Not Met' ? 'bg-red-500' : 'bg-amber-500'

  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2.5">
      <div className="flex items-baseline justify-between gap-3 mb-1.5">
        <span className="text-[11px] font-semibold text-slate-600">
          Coverage {pct}%
          <span className="font-normal text-slate-400">
            {' '}({trace.credit_awarded} of {trace.weight_total} across {trace.applicable_required} required slots)
          </span>
        </span>
        <span className="text-[10px] text-slate-400">{trace.band_applied}</span>
      </div>

      {/* Band markers at the two thresholds, so the bar reads as a decision, not just a number. */}
      <div className="relative h-2 rounded-full bg-slate-100 overflow-hidden">
        <div className={`h-full ${tone} transition-all`} style={{ width: `${pct}%` }} />
        <div className="absolute inset-y-0 border-l border-slate-300" style={{ left: '15%' }} />
        <div className="absolute inset-y-0 border-l border-slate-300" style={{ left: '85%' }} />
      </div>
      <div className="flex justify-between text-[9px] text-slate-400 mt-0.5">
        <span>Not Met</span><span>15%</span><span>Partially Met</span><span>85%</span><span>Met</span>
      </div>

      {gated && (
        <p className="text-[11px] text-red-600 mt-1.5 leading-relaxed">
          <span className="font-semibold">Critical requirement contradicted:</span>{' '}
          {trace.critical_failures.join(', ')} — evidence positively shows this is not done, which
          fails the clause regardless of coverage.
        </p>
      )}
    </div>
  )
}

/**
 * Count line for a filled schema.
 *
 * Counts states rather than `required`, because an analysis result carries the fills but not
 * the schema they came from — `material` on a finding is only true for unfilled required
 * slots, so it cannot stand in for the required count.
 */
export function SlotFillSummary({ fills = [], slots = [] }) {
  if (!fills.length) return null
  const byId = Object.fromEntries(slots.map(s => [s.slot_id, s]))
  // Only required, applicable slots decide the verdict — see derive_clause_state.
  const counted = fills.filter(
    f => byId[f.slot_id]?.required !== false && f.state !== 'not_applicable'
  )
  const filled = counted.filter(f => f.state === 'filled').length
  const partial = counted.filter(f => f.state === 'partially_filled').length
  const unfilled = counted.filter(f => f.state === 'not_filled').length
  return (
    <span className="text-[11px] text-slate-400">
      <span className="text-emerald-600 font-medium">{filled}</span>
      {' of '}{counted.length} required filled
      {partial > 0 && <> · <span className="text-amber-600 font-medium">{partial} partial</span></>}
      {unfilled > 0 && <> · <span className="text-red-500 font-medium">{unfilled} unfilled</span></>}
    </span>
  )
}

/** One slot in the empty schema — what ISO asks for, before any evidence. */
function SchemaSlot({ slot }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-start gap-2 px-3 py-2 text-left hover:bg-slate-50 transition-colors"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-[11px] text-slate-500">{slot.slot_id}</span>
            <RequiredTag required={slot.required} />
            {slot.multiple && (
              <span className="text-[10px] text-slate-400 bg-slate-100 rounded px-1.5 py-0.5">multiple</span>
            )}
          </div>
          <p className="text-xs font-medium text-slate-700 mt-0.5">{slot.label}</p>
          {!open && (
            <p className="text-[11px] text-slate-500 line-clamp-1 mt-0.5">{slot.question}</p>
          )}
        </div>
        <span className="text-[10px] text-slate-400 flex-shrink-0 mt-0.5">
          {VALUE_TYPE_LABELS[slot.value_type] || slot.value_type}
        </span>
      </button>

      {open && (
        <div className="px-3 pb-3 pt-1 space-y-2 border-t border-slate-100">
          <div>
            <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-0.5">Extraction question</p>
            <p className="text-[11px] text-slate-600 leading-relaxed">{slot.question}</p>
          </div>
          {slot.fill_rule && (
            <div>
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-1">When is it filled?</p>
              <div className="space-y-1">
                {['filled', 'partially_filled', 'not_filled'].map(k => (
                  <div key={k} className="flex items-start gap-2">
                    <SlotState state={k} />
                    <p className="text-[11px] text-slate-500 leading-relaxed">{slot.fill_rule[k]}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/** The empty ISO schema for a clause. */
export function SlotSchemaList({ slots = [] }) {
  if (!slots.length) {
    return (
      <div className="text-[11px] text-slate-400 italic">
        No slot schema yet — this clause falls back to a sentence split of its requirements text.
        Generate one with <code className="font-mono not-italic bg-slate-100 rounded px-1">make gen-slots</code>.
      </div>
    )
  }
  return (
    <div className="space-y-1.5">
      {slots.map(s => <SchemaSlot key={s.slot_id} slot={s} />)}
    </div>
  )
}

/**
 * What the evidence established, per slot.
 *
 * `fills` come from the analysis result; `slots` (the schema) is optional and only used to
 * show the human label and the required flag alongside each answer.
 */
/**
 * Fallback label for results stored before the schema was persisted alongside the fills.
 * "responsible_party" -> "Responsible party".
 */
function humanizeSlotId(slotId) {
  const s = String(slotId || '').replace(/_/g, ' ').trim()
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : slotId
}

/** One answered slot. Click to see the question that was actually asked. */
function FilledSlot({ fill, slot }) {
  const [open, setOpen] = useState(false)
  const hasDetail = Boolean(slot?.question || slot?.fill_rule)

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <div
        onClick={() => hasDetail && setOpen(o => !o)}
        className={`flex items-start gap-2 px-3 py-2 ${hasDetail ? 'cursor-pointer hover:bg-slate-50 transition-colors' : ''}`}
      >
        <SlotState state={fill.state} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-medium text-slate-700">{slot?.label || humanizeSlotId(fill.slot_id)}</span>
            {slot && <RequiredTag required={slot.required} />}
          </div>
          {fill.value
            ? <p className="text-[11px] text-slate-600 leading-relaxed mt-0.5">{fill.value}</p>
            : fill.state === 'not_filled' && (
                <p className="text-[11px] text-slate-400 italic mt-0.5">
                  Nothing in the evidence established this.
                </p>
              )}
          {fill.notes && (
            <p className="text-[11px] text-slate-400 italic leading-relaxed mt-0.5">{fill.notes}</p>
          )}
        </div>
        {fill.citation_ids?.length > 0 && (
          <span className="text-[10px] text-slate-400 font-mono flex-shrink-0">
            {fill.citation_ids.map(n => `Chunk ${n}`).join(', ')}
          </span>
        )}
      </div>

      {open && hasDetail && (
        <div className="px-3 pb-3 pt-1 border-t border-slate-100 space-y-1.5">
          {slot.question && (
            <div>
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-0.5">Question asked</p>
              <p className="text-[11px] text-slate-600 leading-relaxed">{slot.question}</p>
            </div>
          )}
          {slot.fill_rule?.[fill.state] && (
            <div>
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide mb-0.5">
                Why this state
              </p>
              <p className="text-[11px] text-slate-500 leading-relaxed">{slot.fill_rule[fill.state]}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function SlotFillList({ fills = [], slots = [] }) {
  const byId = Object.fromEntries(slots.map(s => [s.slot_id, s]))
  if (!fills.length) return null

  // Unanswered required slots are what decided the verdict, so they lead.
  const order = { not_filled: 0, partially_filled: 1, not_applicable: 2, filled: 3 }
  const rank = f => (order[f.state] ?? 9) + (byId[f.slot_id]?.required === false ? 0.5 : 0)
  const sorted = [...fills].sort((a, b) => rank(a) - rank(b))

  return (
    <div className="space-y-1.5">
      {sorted.map(f => <FilledSlot key={f.slot_id} fill={f} slot={byId[f.slot_id]} />)}
    </div>
  )
}

/**
 * A title-only ISO clause's result — e.g. 6.2 "Environmental objectives and planning to
 * achieve them", which has no normative text of its own (ISO 14001 marks it a heading; the
 * "shall" text starts only at 6.2.1). Such a clause is never independently analysed, so it
 * has no slot_schema/slot_fills of its own — its `children_summary` (from the API) is
 * pooled coverage over its real children's real slots, plus each child's own fills grouped
 * by sub-clause. The parent's decision itself is still worst-child-wins, computed
 * separately in `aggregate_parent_decisions` — this coverage number is for transparency,
 * not what decided the verdict.
 */
export function ChildrenSummary({ summary }) {
  if (!summary) return null
  const pct = summary.weight_total > 0 ? Math.round(summary.coverage * 100) : null

  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5">
        <p className="text-[11px] text-slate-500 leading-relaxed">
          <span className="font-semibold text-slate-600">Section — </span>
          this clause is an ISO 14001 heading with no requirements of its own; everything
          below comes from its sub-clauses.
          {pct !== null && (
            <>
              {' '}Pooled coverage across {summary.applicable_required} required slot
              {summary.applicable_required === 1 ? '' : 's'}: <span className="font-semibold text-slate-700">{pct}%</span>.
            </>
          )}
        </p>
      </div>

      {(summary.children || []).map(child => (
        <div key={child.clause_id}>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="font-mono text-xs bg-slate-100 text-slate-700 rounded px-1.5 py-0.5">
              {child.clause_id}
            </span>
            <span className="text-xs font-semibold text-slate-700">{child.title}</span>
            <span className="text-[11px] text-slate-400">{child.decision}</span>
          </div>
          {child.slot_fills?.length > 0 ? (
            <SlotFillList fills={child.slot_fills} slots={child.slot_schema} />
          ) : (
            <p className="text-[11px] text-slate-400 italic pl-1">
              No slots recorded for {child.clause_id} — it may have abstained on insufficient evidence.
            </p>
          )}
        </div>
      ))}
    </div>
  )
}
