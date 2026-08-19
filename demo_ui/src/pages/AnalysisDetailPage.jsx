import { useEffect, useState, useRef, useMemo, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  getAnalysis, pauseAnalysis, resumeAnalysis, deleteAnalysis,
  getResults, getRecommendations, getMissingRequirements, downloadReport,
  getStaleness, reanalyzeDelta,
} from '../api/analyses.js'
import { useJobProgress } from '../hooks/useJobProgress.js'
import Badge from '../components/Badge.jsx'
import Spinner from '../components/Spinner.jsx'
import MarkdownContent from '../components/MarkdownContent.jsx'
import StalenessBanner from '../components/StalenessBanner.jsx'

const ACTIVE = ['pending', 'running', 'paused']
const DONE   = ['complete', 'failed']

function compareClauseIds(a, b) {
  const pa = String(a).split('.').map(Number)
  const pb = String(b).split('.').map(Number)
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const diff = (pa[i] ?? 0) - (pb[i] ?? 0)
    if (diff !== 0) return diff
  }
  return 0
}

const ChevronUp = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M5 15l7-7 7 7" />
  </svg>
)
const ChevronDown = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
  </svg>
)
const XCircle = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5 text-red-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
)
const CloseSVG = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
  </svg>
)

// ── Citation Modal ────────────────────────────────────────────────────────────
function CitationModal({ citation, onClose }) {
  if (!citation) return null
  const title = citation.type === 'org_profile'
    ? (citation.field_path || 'Organisation Profile')
    : (citation.filename || 'Document Reference')
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl max-w-lg w-full max-h-[80vh] flex flex-col animate-fade-in-up"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-slate-100">
          <div className="min-w-0">
            <p className="font-semibold text-slate-800 text-sm truncate">{title}</p>
            {citation.type !== 'org_profile' && citation.page != null && (
              <p className="text-xs text-slate-500 mt-0.5">Page {citation.page}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 hover:bg-slate-100 p-1.5 rounded-full transition-colors flex-shrink-0"
          >
            <CloseSVG />
          </button>
        </div>
        <div className="p-5 overflow-y-auto">
          <div className="bg-slate-50 border border-slate-100 rounded-xl p-4 text-sm text-slate-700 leading-relaxed">
            <MarkdownContent content={citation.text || 'No excerpt available.'} />
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Live Progress Panel ──────────────────────────────────────────────────────
function ProgressPanel({ analysisId, currentClauseId = null, initialGapCount = 0, onClauseComplete, onAnalysisDone }) {
  const clauseLogRef = useRef()
  const [fetchedCompleted, setFetchedCompleted] = useState(0)

  const { messages, status, isConnected } = useJobProgress(analysisId, {})

  useEffect(() => {
    getResults(analysisId)
      .then(r => setFetchedCompleted((r || []).length))
      .catch(() => {})
  }, [analysisId])

  const { completed: wsCompleted, total, gapCount: wsGapCount, thinkingClause, currentStage, clauseLog } = useMemo(() => {
    let completed = 0, total = 32, gapCount = 0, thinkingClause = null, currentStage = null
    const clauseMap = new Map()
    for (const m of messages) {
      if (m.completed != null) completed = m.completed
      if (m.total != null) total = m.total
      if (m.gap_count != null) gapCount = m.gap_count
      if (m.stage === 'thinking') {
        thinkingClause = m.clause_id || null
        currentStage = null  // reset sub-step when a new clause starts
      } else if (m.stage === 'clause_stage') {
        currentStage = m  // { step, step_index, step_total, detail, clause_id }
      } else if (m.stage === 'clause') {
        thinkingClause = null
        currentStage = null  // clear sub-step when clause completes
        if (m.clause_id) clauseMap.set(m.clause_id, { clause_id: m.clause_id, decision: m.decision || '' })
      }
    }
    return { completed, total, gapCount, thinkingClause, currentStage, clauseLog: Array.from(clauseMap.values()).sort((a, b) => compareClauseIds(a.clause_id, b.clause_id)) }
  }, [messages])

  useEffect(() => {
    const last = messages[messages.length - 1]
    if (last?.stage === 'clause') {
      onClauseComplete?.()
    }
  }, [messages])

  // Notify parent immediately when WS signals the analysis is done/failed
  useEffect(() => {
    if (status === 'done' || status === 'failed') {
      onAnalysisDone?.()
    }
  }, [status])

  const completed = Math.max(wsCompleted, fetchedCompleted)
  const gapCount = wsGapCount > 0 ? wsGapCount : initialGapCount
  const activeClause = thinkingClause || (messages.length === 0 ? currentClauseId : null)
  const pct = Math.min((completed / total) * 100, 100)

  useEffect(() => {
    if (clauseLogRef.current)
      clauseLogRef.current.scrollTop = clauseLogRef.current.scrollHeight
  }, [clauseLog.length])

  const decisionBorder = (d) => {
    if (d === 'Met') return 'border-l-emerald-500 text-emerald-700 bg-emerald-50'
    if (d === 'Partially Met') return 'border-l-amber-500 text-amber-700 bg-amber-50'
    if (d === 'Insufficient Evidence') return 'border-l-amber-400 text-amber-700 bg-amber-50'
    return 'border-l-red-500 text-red-700 bg-red-50'
  }

  return (
    <div className="rounded-xl bg-white border border-slate-200 shadow-sm p-5 space-y-4">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isConnected
            ? <Spinner size="sm" />
            : messages.length > 0
              ? <span className="text-amber-500 text-xs font-medium">Reconnecting…</span>
              : <Spinner size="sm" />}
          <span className="text-sm font-semibold text-slate-800">
            Live Progress
          </span>
          <span className="text-xs text-slate-400">{completed} / {total} clauses</span>
        </div>
        {gapCount > 0 && (
          <span className="text-xs font-bold text-red-600 bg-red-100 rounded-full px-2.5 py-0.5">
            {gapCount} gap{gapCount !== 1 ? 's' : ''} found
          </span>
        )}
      </div>

      {/* Progress bar */}
      <div>
        <div className="h-3 rounded-full bg-slate-100 overflow-hidden">
          <div
            className="h-3 rounded-full bg-gradient-to-r from-brand-400 to-brand-600 transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        <p className="text-xs text-slate-400 mt-1">{pct.toFixed(0)}% complete</p>
      </div>

      {/* Currently analysing indicator */}
      {activeClause && (
        <div className="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 flex items-start gap-3">
          <span className="mt-0.5 w-2 h-2 rounded-full bg-blue-500 animate-pulse flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-blue-800">
              Analysing clause <span className="font-mono">{activeClause}</span>
            </p>
            {currentStage && (
              <div className="mt-2 space-y-1">
                <p className="text-xs text-blue-600 truncate">{currentStage.detail}</p>
                <div className="h-1 rounded-full bg-blue-100 overflow-hidden">
                  <div
                    className="h-1 rounded-full bg-blue-400 transition-all duration-300"
                    style={{ width: `${Math.min((currentStage.step_index / currentStage.step_total) * 100, 100)}%` }}
                  />
                </div>
              </div>
            )}
          </div>
          {currentStage && (
            <span className="text-xs text-blue-500 font-medium flex-shrink-0">
              {currentStage.step_index}/{currentStage.step_total}
            </span>
          )}
        </div>
      )}

      {/* Clause decision log */}
      <div ref={clauseLogRef} className="max-h-44 overflow-y-auto space-y-1 scrollbar-thin">
        {clauseLog.length === 0 && !activeClause && (
          <p className="text-xs text-slate-400 pl-1">Waiting for first clause result…</p>
        )}
        {activeClause && !clauseLog.find(e => e.clause_id === activeClause) && (
          <div className="flex items-center gap-2 text-xs border-l-2 border-l-blue-500 bg-blue-50 rounded-r px-2 py-1.5 text-blue-700 animate-pulse">
            <span className="font-mono font-semibold w-10 flex-shrink-0">{activeClause}</span>
            <span>Analysing…</span>
          </div>
        )}
        {clauseLog.map((entry) => (
          <div
            key={entry.clause_id}
            className={`flex items-center gap-2 text-xs border-l-2 rounded-r px-2 py-1.5 ${decisionBorder(entry.decision)}`}
          >
            <span className="font-mono font-semibold w-10 flex-shrink-0">{entry.clause_id}</span>
            <span>{entry.decision}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Gap Results Tab ──────────────────────────────────────────────────────────
function GapResultsTab({ analysisId, version }) {
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(null)
  const [activeCitation, setActiveCitation] = useState(null)

  useEffect(() => {
    getResults(analysisId).then(r => { setResults((r || []).sort((a, b) => compareClauseIds(a.clause_id, b.clause_id))); setLoading(false) })
  }, [analysisId, version])

  if (loading) return <div className="flex justify-center py-10"><Spinner size="lg" /></div>
  if (!results.length) return <p className="text-sm text-slate-400 py-6">No results yet.</p>

  const counts = results.reduce((acc, r) => {
    acc[r.decision] = (acc[r.decision] || 0) + 1; return acc
  }, {})

  const summaryStyle = (d) => {
    if (d === 'Met') return 'bg-emerald-50 border-emerald-200 text-emerald-700'
    if (d === 'Partially Met') return 'bg-amber-50 border-amber-200 text-amber-700'
    if (d === 'Not Met') return 'bg-red-50 border-red-200 text-red-700'
    return 'bg-slate-50 border-slate-200 text-slate-600'
  }

  const expandedBorder = (d) => {
    if (d === 'Met') return 'border-l-emerald-500'
    if (d === 'Partially Met') return 'border-l-amber-500'
    if (d === 'Not Met') return 'border-l-red-500'
    return 'border-l-slate-400'
  }

  return (
    <div className="space-y-4">
      {/* Summary chips */}
      <div className="flex flex-wrap gap-3">
        {Object.entries(counts).map(([d, n]) => (
          <div key={d} className={`rounded-xl border px-4 py-3 text-center min-w-[80px] ${summaryStyle(d)}`}>
            <div className="text-2xl font-bold">{n}</div>
            <div className="text-xs mt-0.5">{d}</div>
          </div>
        ))}
      </div>

      {/* Accordion */}
      <div className="rounded-xl border border-slate-200 overflow-hidden divide-y divide-slate-100">
        {results.map(r => (
          <div key={r.clause_id}>
            <button
              onClick={() => setExpanded(expanded === r.clause_id ? null : r.clause_id)}
              className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-slate-50 transition-colors"
            >
              <span className="font-mono text-xs bg-slate-100 text-slate-600 rounded px-1.5 py-0.5 w-12 text-center flex-shrink-0">{r.clause_id}</span>
              <Badge status={r.decision} />
              <div className="flex-1" />
              <span className="text-slate-400">{expanded === r.clause_id ? <ChevronUp /> : <ChevronDown />}</span>
            </button>
            {expanded === r.clause_id && (
              <div className={`px-4 pb-4 pt-2 bg-slate-50 border-l-4 space-y-3 ${expandedBorder(r.decision)}`}>
                <div>
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Reasoning</p>
                  <p className="text-xs text-slate-700 leading-relaxed">{r.reasoning}</p>
                </div>
                {r.missing_evidence?.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Missing Evidence</p>
                    <ul className="space-y-1">
                      {r.missing_evidence.map((e, i) => (
                        <li key={i} className="flex items-start gap-1.5 text-xs text-red-600">
                          <XCircle />
                          {e}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {r.citations?.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Citations</p>
                    <div className="flex flex-wrap gap-2">
                      {r.citations.map((c, i) => (
                        <button
                          key={i}
                          onClick={() => setActiveCitation(c)}
                          className="text-xs bg-white border border-slate-200 rounded px-2 py-0.5 text-slate-500 hover:border-brand-300 hover:text-brand-700 hover:bg-brand-50 transition-colors cursor-pointer"
                        >
                          {c.type === 'org_profile'
                            ? c.field_path
                            : `${c.filename || c.chunk_id}${c.page != null ? ` p.${c.page}` : ''}`}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      <CitationModal citation={activeCitation} onClose={() => setActiveCitation(null)} />
    </div>
  )
}

// ── Recommendations Tab ──────────────────────────────────────────────────────
function RecommendationCard({ rec, rank, activeSort, showClauseBadge = false }) {
  function Stars({ n, max = 5, color = 'text-amber-400' }) {
    const validN = Math.max(0, Math.min(max, Number(n) || 0))
    return (
      <span className={`${color} font-mono tracking-tighter`} title={`${validN}/${max}`}>
        {'★'.repeat(validN)}{'☆'.repeat(max - validN)}
      </span>
    )
  }

  return (
    <div className="rounded-xl bg-white border border-slate-200 shadow-sm p-4 hover:border-brand-300 hover:shadow-md transition-all duration-200 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5 flex-1 min-w-0">
          {rank != null && (
            <span className="font-mono text-xs font-bold text-slate-400 bg-slate-100 rounded-md px-1.5 py-0.5 flex-shrink-0 mt-0.5">
              #{rank}
            </span>
          )}
          {showClauseBadge && (
            <span className="font-mono text-xs font-semibold bg-brand-50 text-brand-700 border border-brand-200 rounded-md px-2 py-0.5 flex-shrink-0 mt-0.5">
              Clause {rec.clause_id}
            </span>
          )}
          <p className="text-sm text-slate-800 leading-relaxed flex-1">{rec.text}</p>
        </div>
      </div>

      {/* Metric Badges */}
      <div className="flex flex-wrap items-center gap-2.5 pt-2 border-t border-slate-100 text-xs">
        {/* Impact */}
        <div className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 transition-all ${
          activeSort === 'impact'
            ? 'bg-emerald-100 text-emerald-800 border-2 border-emerald-400 font-semibold shadow-xs'
            : 'bg-emerald-50 text-emerald-700 border border-emerald-200/70'
        }`}>
          <span className="text-[11px] uppercase tracking-wide">Impact</span>
          <Stars n={rec.impact} color={activeSort === 'impact' ? 'text-emerald-600' : 'text-emerald-500'} />
          <span className="text-[11px] font-bold">({rec.impact ?? 0}/5)</span>
        </div>

        {/* Cost */}
        <div className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 transition-all ${
          activeSort === 'cost'
            ? 'bg-rose-100 text-rose-800 border-2 border-rose-400 font-semibold shadow-xs'
            : 'bg-rose-50 text-rose-700 border border-rose-200/70'
        }`}>
          <span className="text-[11px] uppercase tracking-wide">Cost</span>
          <Stars n={rec.cost} color={activeSort === 'cost' ? 'text-rose-600' : 'text-rose-400'} />
          <span className="text-[11px] font-bold">({rec.cost ?? 0}/5)</span>
        </div>

        {/* Effort */}
        <div className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 transition-all ${
          activeSort === 'effort'
            ? 'bg-indigo-100 text-indigo-800 border-2 border-indigo-400 font-semibold shadow-xs'
            : 'bg-indigo-50 text-indigo-700 border border-indigo-200/70'
        }`}>
          <span className="text-[11px] uppercase tracking-wide">Effort</span>
          <strong className="text-slate-800 font-mono text-[12px]">{rec.effort_weeks ?? 0}w</strong>
          <span className="text-[10px] text-slate-500">({(rec.effort_weeks ?? 0) * 5}d)</span>
        </div>
      </div>
    </div>
  )
}

function RecommendationsTab({ analysisId, version }) {
  const [recs, setRecs] = useState([])
  const [loading, setLoading] = useState(true)
  const [sortBy, setSortBy] = useState('clause') // 'clause' | 'cost' | 'effort' | 'impact'
  const [sortOrder, setSortOrder] = useState('asc') // 'asc' | 'desc'

  useEffect(() => {
    getRecommendations(analysisId).then(r => { setRecs(r || []); setLoading(false) })
  }, [analysisId, version])

  function handleSortChange(newSort) {
    if (sortBy === newSort) {
      setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(newSort)
      if (newSort === 'impact') {
        setSortOrder('desc')
      } else if (newSort === 'cost' || newSort === 'effort') {
        setSortOrder('asc')
      } else {
        setSortOrder('asc')
      }
    }
  }

  const sortedRecs = useMemo(() => {
    const list = [...recs]
    const dir = sortOrder === 'asc' ? 1 : -1

    return list.sort((a, b) => {
      if (sortBy === 'cost') {
        const diff = ((a.cost ?? 0) - (b.cost ?? 0)) * dir
        if (diff !== 0) return diff
        return compareClauseIds(a.clause_id, b.clause_id)
      }
      if (sortBy === 'effort') {
        const diff = ((a.effort_weeks ?? 0) - (b.effort_weeks ?? 0)) * dir
        if (diff !== 0) return diff
        return compareClauseIds(a.clause_id, b.clause_id)
      }
      if (sortBy === 'impact') {
        const diff = ((a.impact ?? 0) - (b.impact ?? 0)) * dir
        if (diff !== 0) return diff
        return compareClauseIds(a.clause_id, b.clause_id)
      }
      // default: clause
      return compareClauseIds(a.clause_id, b.clause_id) * dir
    })
  }, [recs, sortBy, sortOrder])

  if (loading) return <div className="flex justify-center py-10"><Spinner size="lg" /></div>
  if (!recs.length) return <p className="text-sm text-slate-400 py-6">No recommendations yet. Run and complete an analysis first.</p>

  const isGrouped = sortBy === 'clause'

  // When grouped by clause
  const byClause = sortedRecs.reduce((acc, r) => {
    ;(acc[r.clause_id] = acc[r.clause_id] || []).push(r); return acc
  }, {})

  const sortedClauseKeys = Object.keys(byClause).sort((a, b) => {
    return compareClauseIds(a, b) * (sortOrder === 'asc' ? 1 : -1)
  })

  return (
    <div className="space-y-5">
      {/* Sorting Toolbar */}
      <div className="rounded-xl bg-slate-50 border border-slate-200/80 p-3.5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
              <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 4h13M3 8h9m-9 4h6m4 0l4-4m0 0l4 4m-4-4v12" />
              </svg>
              Sort by:
            </span>

            <div className="flex items-center gap-1 bg-white p-1 rounded-lg border border-slate-200 shadow-xs">
              {[
                { key: 'clause', label: 'Clause' },
                { key: 'impact', label: 'Impact' },
                { key: 'cost', label: 'Cost' },
                { key: 'effort', label: 'Effort' },
              ].map(opt => {
                const isActive = sortBy === opt.key
                return (
                  <button
                    key={opt.key}
                    onClick={() => handleSortChange(opt.key)}
                    className={`px-3 py-1 text-xs font-semibold rounded-md transition-all flex items-center gap-1.5 cursor-pointer ${
                      isActive
                        ? 'bg-brand-600 text-white shadow-xs'
                        : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                    }`}
                  >
                    {opt.label}
                    {isActive && (
                      <span className="text-[10px] opacity-90 font-mono">
                        {sortOrder === 'asc' ? '▲' : '▼'}
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc')}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-600 bg-white border border-slate-200 hover:bg-slate-100 px-3 py-1.5 rounded-lg transition-colors shadow-xs cursor-pointer"
              title="Toggle sort direction"
            >
              <span>Order:</span>
              <strong className="text-slate-800">
                {sortBy === 'clause'
                  ? (sortOrder === 'asc' ? 'Clause (4.1 → 10.3)' : 'Clause (10.3 → 4.1)')
                  : (sortOrder === 'desc' ? 'Highest First (High → Low)' : 'Lowest First (Low → High)')}
              </strong>
              <span className="text-slate-400 font-mono">{sortOrder === 'asc' ? '↑' : '↓'}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Render Recommendations List */}
      {isGrouped ? (
        /* Grouped by clause */
        <div className="space-y-6">
          {sortedClauseKeys.map((clauseId) => (
            <div key={clauseId} className="space-y-3">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs font-bold bg-brand-50 text-brand-700 border border-brand-200 rounded-md px-2 py-0.5">
                  Clause {clauseId}
                </span>
                <span className="text-xs text-slate-400">
                  {byClause[clauseId].length} recommendation{byClause[clauseId].length !== 1 ? 's' : ''}
                </span>
              </div>
              <div className="space-y-3">
                {byClause[clauseId].map((rec, i) => (
                  <RecommendationCard key={i} rec={rec} activeSort={sortBy} />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* Sorted Flat List (e.g. prioritized by impact, cost, or effort) */
        <div className="space-y-3">
          {sortedRecs.map((rec, i) => (
            <RecommendationCard key={i} rec={rec} rank={i + 1} activeSort={sortBy} showClauseBadge />
          ))}
        </div>
      )}
    </div>
  )
}

// ── Missing Requirements Tab ─────────────────────────────────────────────────
function MissingRequirementsTab({ analysisId, version }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [copied, setCopied] = useState(null)

  useEffect(() => {
    getMissingRequirements(analysisId).then(r => { setItems(r || []); setLoading(false) })
  }, [analysisId, version])

  if (loading) return <div className="flex justify-center py-10"><Spinner size="lg" /></div>
  if (!items.length) return <p className="text-sm text-slate-400 py-6">No missing requirement requests yet.</p>

  const byClause = items.reduce((acc, r) => {
    ;(acc[r.clause_id] = acc[r.clause_id] || []).push(r); return acc
  }, {})

  function copy(text, key) {
    navigator.clipboard.writeText(text)
    setCopied(key)
    setTimeout(() => setCopied(null), 1500)
  }

  return (
    <div className="space-y-5">
      {Object.entries(byClause).sort(([a], [b]) => compareClauseIds(a, b)).map(([clauseId, reqs]) => (
        <div key={clauseId}>
          <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Clause {clauseId}</h4>
          <div className="space-y-3">
            {reqs.map((req, i) => {
              const key = `${clauseId}-${i}`
              return (
                <div key={i} className="rounded-xl bg-white border border-slate-200 shadow-sm p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1">
                      <p className="text-xs text-brand-600 font-mono mb-1">{req.field_path}</p>
                      <p className="text-sm text-slate-700 leading-relaxed">{req.request_text}</p>
                    </div>
                    <button
                      onClick={() => copy(req.request_text, key)}
                      className="flex-shrink-0 text-xs font-medium text-slate-400 hover:text-slate-700 border border-slate-200 hover:border-slate-300 rounded px-2 py-1 transition-colors"
                    >
                      {copied === key ? '✓ Copied' : 'Copy'}
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Main Page ────────────────────────────────────────────────────────────────
export default function AnalysisDetailPage() {
  const { profileId, analysisId: id } = useParams()
  const navigate = useNavigate()
  const [analysis, setAnalysis] = useState(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('results')
  const [actioning, setActioning] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [resultVersion, setResultVersion] = useState(0)
  const [staleness, setStaleness] = useState(null)
  const [reanalyzing, setReanalyzing] = useState(false)
  const [deleting, setDeleting] = useState(false)

  async function refresh() {
    const a = await getAnalysis(id).catch(() => null)
    if (a) setAnalysis(a)
  }

  const handleClauseComplete = useCallback(() => {
    setResultVersion(v => v + 1)
  }, [])

  const handleAnalysisDone = useCallback(() => {
    setResultVersion(v => v + 1)
    refresh()
  }, [])

  useEffect(() => {
    refresh().finally(() => setLoading(false))

    const iv = setInterval(async () => {
      const a = await getAnalysis(id).catch(() => null)
      if (!a) return
      setAnalysis(a)
      if (DONE.includes(a.status)) clearInterval(iv)
    }, 6000)
    return () => clearInterval(iv)
  }, [id])

  async function handlePause() {
    setActioning(true)
    try {
      await pauseAnalysis(id)
      setAnalysis(prev => prev ? { ...prev, status: 'paused' } : prev)
      await refresh()
    } catch (err) { alert(err.message) }
    setActioning(false)
  }

  async function handleResume() {
    setActioning(true)
    try {
      await resumeAnalysis(id)
      setAnalysis(prev => prev ? { ...prev, status: 'running' } : prev)
      await refresh()
    } catch (err) { alert(err.message) }
    setActioning(false)
  }

  async function handleDelete() {
    if (!window.confirm('Are you sure you want to delete this analysis report? All results, recommendations, and missing requirements for this analysis will be permanently deleted.')) {
      return
    }
    setDeleting(true)
    try {
      await deleteAnalysis(id)
      navigate(`/analyses/${profileId}`)
    } catch (err) {
      alert(err.message || 'Failed to delete analysis')
      setDeleting(false)
    }
  }

  // Once the analysis is complete, check whether documents have changed since it ran.
  useEffect(() => {
    if (analysis?.status !== 'complete') { setStaleness(null); return }
    let cancelled = false
    getStaleness(id)
      .then(s => { if (!cancelled) setStaleness(s) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [id, analysis?.status, resultVersion])

  async function handleReanalyze() {
    setReanalyzing(true)
    try {
      const res = await reanalyzeDelta(id)
      navigate(`/analyses/${profileId}/${res.analysis_id}`)
    } catch (err) {
      alert(err.message)
      setReanalyzing(false)
    }
  }

  async function handleExport() {
    setExporting(true)
    try {
      const blob = await downloadReport(id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `compliance-report-${id.slice(0, 8)}.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (err) { alert(err.message) }
    setExporting(false)
  }

  if (loading) return <div className="flex justify-center py-20"><Spinner size="lg" /></div>
  if (!analysis) return <p className="text-center text-slate-400 py-20">Analysis not found.</p>

  const isActive = ACTIVE.includes(analysis.status)

  const TABS = [
    ['results', 'Gap Results'],
    ['recommendations', 'Recommendations'],
    ['missing', 'Missing Requirements'],
  ]

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      {/* Header card */}
      <div className="rounded-xl bg-white border border-slate-200 shadow-sm p-5">
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div>
            <button onClick={() => navigate(`/analyses/${profileId}`)} className="text-xs text-slate-400 hover:text-brand-600 mb-1 transition-colors">
              ← Analyses
            </button>
            <h1 className="text-xl font-bold text-slate-900">Analysis Detail</h1>
            <p className="text-xs text-slate-400 mt-1 font-mono">{analysis.analysis_id}</p>
            <p className="text-xs text-slate-400">{new Date(analysis.created_at).toLocaleString()}</p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <Badge status={analysis.status} />
            {analysis.status === 'complete' && (
              <button
                onClick={handleExport}
                disabled={exporting}
                className="flex items-center gap-1.5 rounded-lg border border-brand-300 bg-brand-50 px-3 py-1.5 text-xs font-semibold text-brand-700 hover:bg-brand-100 disabled:opacity-60 transition-colors cursor-pointer"
              >
                {exporting
                  ? <Spinner size="sm" />
                  : <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m-9 7h12a2 2 0 002-2V7a2 2 0 00-2-2h-5.586a1 1 0 01-.707-.293l-1.414-1.414A1 1 0 009.586 3H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>}
                {exporting ? 'Generating…' : 'Export PDF'}
              </button>
            )}
            {analysis.gap_count != null && (
              <span className={`text-sm font-bold rounded-full px-3 py-0.5 ${
                analysis.gap_count > 0 ? 'bg-red-100 text-red-700' : 'bg-emerald-100 text-emerald-700'
              }`}>
                {analysis.gap_count} gap{analysis.gap_count !== 1 ? 's' : ''}
              </span>
            )}
            {isActive && analysis.status !== 'paused' && (
              <button
                onClick={handlePause}
                disabled={actioning}
                className="flex items-center gap-1.5 rounded-lg border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-700 hover:bg-amber-100 disabled:opacity-60 transition-colors cursor-pointer"
              >
                {actioning && <Spinner size="sm" />}
                <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
                Pause
              </button>
            )}
            {analysis.status === 'paused' && (
              <button
                onClick={handleResume}
                disabled={actioning}
                className="flex items-center gap-1.5 rounded-lg border border-brand-300 bg-brand-50 px-3 py-1.5 text-xs font-semibold text-brand-700 hover:bg-brand-100 disabled:opacity-60 transition-colors cursor-pointer"
              >
                {actioning && <Spinner size="sm" />}
                <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                Resume
              </button>
            )}
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="flex items-center gap-1.5 rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-100 disabled:opacity-60 transition-colors cursor-pointer"
              title="Delete this analysis report"
            >
              {deleting ? (
                <Spinner size="sm" />
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              )}
              Delete
            </button>
          </div>
        </div>
      </div>

      {/* Staleness banner — documents changed since this analysis ran */}
      {analysis.status === 'complete' && (
        <StalenessBanner staleness={staleness} onReanalyze={handleReanalyze} reanalyzing={reanalyzing} />
      )}

      {/* Delta badge — this analysis was an incremental re-run */}
      {analysis.mode === 'delta' && (
        <div className="rounded-xl border border-brand-200 bg-brand-50 px-4 py-2.5 flex items-center gap-2 text-xs text-brand-700">
          <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          <span>Incremental re-analysis — only clauses affected by changed evidence were re-run; other verdicts carried over.</span>
        </div>
      )}

      {/* Live progress */}
      {(analysis.status === 'running' || analysis.status === 'pending') && <ProgressPanel analysisId={id} currentClauseId={analysis.current_clause_id} initialGapCount={analysis.gap_count ?? 0} onClauseComplete={handleClauseComplete} onAnalysisDone={handleAnalysisDone} />}
      {analysis.status === 'paused' && (
        <div className="rounded-xl bg-white border border-slate-200 shadow-sm p-5 flex items-center gap-3 text-sm text-slate-500">
          <svg className="w-4 h-4 text-amber-500 flex-shrink-0" fill="currentColor" viewBox="0 0 24 24">
            <rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>
          </svg>
          Analysis is paused. Click <span className="font-semibold text-brand-600">Resume</span> to continue.
        </div>
      )}

      {/* Pill tabs */}
      <div className="overflow-x-auto">
        <div className="flex gap-1 bg-slate-100 p-1 rounded-xl w-fit min-w-full sm:min-w-0">
          {TABS.map(([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`px-4 py-2 text-sm font-medium rounded-lg whitespace-nowrap transition-all ${
                tab === key
                  ? 'bg-white shadow-sm text-slate-900'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="rounded-xl bg-white border border-slate-200 shadow-sm p-5">
        {tab === 'results'          && <GapResultsTab analysisId={id} version={resultVersion} />}
        {tab === 'recommendations'  && <RecommendationsTab analysisId={id} version={resultVersion} />}
        {tab === 'missing'          && <MissingRequirementsTab analysisId={id} version={resultVersion} />}
      </div>
    </div>
  )
}
