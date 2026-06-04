import { useEffect, useState, useRef, useMemo, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import {
  getAnalysis, pauseAnalysis, resumeAnalysis,
  getResults, getRecommendations, getMissingRequirements,
} from '../api/analyses.js'
import { useJobProgress } from '../hooks/useJobProgress.js'
import Badge from '../components/Badge.jsx'
import Spinner from '../components/Spinner.jsx'

const ACTIVE = ['pending', 'running']
const DONE   = ['complete', 'failed', 'paused']

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

// ── Live Progress Panel ──────────────────────────────────────────────────────
function ProgressPanel({ analysisId, currentClauseId = null, initialGapCount = 0, onClauseComplete, onAnalysisDone }) {
  const [thinkingText, setThinkingText] = useState('')
  const terminalRef = useRef()
  const bottomRef = useRef()
  const [fetchedCompleted, setFetchedCompleted] = useState(0)

  const { messages, status, isConnected } = useJobProgress(analysisId, {
    onThinkingToken: useCallback((m) => {
      setThinkingText(prev => prev + m.detail)
    }, []),
  })

  useEffect(() => {
    getResults(analysisId)
      .then(r => setFetchedCompleted((r || []).length))
      .catch(() => {})
  }, [analysisId])

  const { completed: wsCompleted, total, gapCount: wsGapCount, thinkingClause, thinkingDetail, clauseLog } = useMemo(() => {
    let completed = 0, total = 32, gapCount = 0, thinkingClause = null, thinkingDetail = null
    const clauseMap = new Map()
    for (const m of messages) {
      if (m.completed != null) completed = m.completed
      if (m.total != null) total = m.total
      if (m.gap_count != null) gapCount = m.gap_count
      if (m.stage === 'thinking') {
        thinkingClause = m.clause_id || null
        thinkingDetail = m.detail || null
      } else if (m.stage === 'clause') {
        thinkingClause = null
        thinkingDetail = null
        if (m.clause_id) clauseMap.set(m.clause_id, { clause_id: m.clause_id, decision: m.decision || '' })
      }
    }
    return { completed, total, gapCount, thinkingClause, thinkingDetail, clauseLog: Array.from(clauseMap.values()) }
  }, [messages])

  useEffect(() => {
    const last = messages[messages.length - 1]
    if (last?.stage === 'thinking' || last?.stage === 'clause') {
      setThinkingText('')
    }
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
    if (terminalRef.current)
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight
  }, [thinkingText])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
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

      {/* Thinking terminal */}
      {(activeClause || thinkingText) && (
        <div className="rounded-lg bg-gray-950 border border-gray-800 overflow-hidden">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-900 border-b border-gray-800">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500 opacity-70" />
            <span className="w-2.5 h-2.5 rounded-full bg-yellow-500 opacity-70" />
            <span className="w-2.5 h-2.5 rounded-full bg-green-500 opacity-70" />
            <span className="text-xs text-gray-400 ml-2 font-mono">
              Compliance reasoning — clause {activeClause || '…'}
            </span>
          </div>
          <div
            ref={terminalRef}
            className="px-4 py-3 font-mono text-[11px] text-emerald-300 leading-relaxed whitespace-pre-wrap max-h-52 overflow-y-auto scrollbar-thin"
          >
            {thinkingText || (
              <span className="text-gray-500 italic">
                {thinkingDetail || 'Preparing analysis…'}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Clause decision log */}
      <div className="max-h-44 overflow-y-auto space-y-1 scrollbar-thin">
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
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

// ── Gap Results Tab ──────────────────────────────────────────────────────────
function GapResultsTab({ analysisId, version }) {
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(null)

  useEffect(() => {
    getResults(analysisId).then(r => { setResults(r || []); setLoading(false) })
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
                        <span key={i} className="text-xs bg-white border border-slate-200 rounded px-2 py-0.5 text-slate-500">
                          {c.filename || c.chunk_id} p.{c.page}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Recommendations Tab ──────────────────────────────────────────────────────
function RecommendationsTab({ analysisId, version }) {
  const [recs, setRecs] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getRecommendations(analysisId).then(r => { setRecs(r || []); setLoading(false) })
  }, [analysisId, version])

  if (loading) return <div className="flex justify-center py-10"><Spinner size="lg" /></div>
  if (!recs.length) return <p className="text-sm text-slate-400 py-6">No recommendations yet. Run and complete an analysis first.</p>

  const byClause = recs.reduce((acc, r) => {
    ;(acc[r.clause_id] = acc[r.clause_id] || []).push(r); return acc
  }, {})

  function Stars({ n, max = 5, color = 'text-amber-400' }) {
    return (
      <span className={color}>
        {'★'.repeat(n)}{'☆'.repeat(max - n)}
      </span>
    )
  }

  return (
    <div className="space-y-5">
      {Object.entries(byClause).map(([clauseId, items]) => (
        <div key={clauseId}>
          <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">
            Clause {clauseId}
          </h4>
          <div className="space-y-3">
            {items.map((rec, i) => (
              <div key={i} className="rounded-xl bg-white border border-slate-200 shadow-sm p-4">
                <p className="text-sm text-slate-800 mb-3">{rec.text}</p>
                <div className="flex flex-wrap gap-4 text-xs text-slate-500">
                  <span>Cost: <Stars n={rec.cost} color="text-red-400" /></span>
                  <span>Impact: <Stars n={rec.impact} color="text-brand-500" /></span>
                  <span>Effort: <strong className="text-slate-700">{rec.effort_weeks}w</strong></span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
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
      {Object.entries(byClause).map(([clauseId, reqs]) => (
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
  const { id } = useParams()
  const [analysis, setAnalysis] = useState(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('results')
  const [actioning, setActioning] = useState(false)
  const [resultVersion, setResultVersion] = useState(0)

  async function refresh() {
    const a = await getAnalysis(id).catch(() => null)
    setAnalysis(a)
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
    try { await pauseAnalysis(id); await refresh() } catch (err) { alert(err.message) }
    setActioning(false)
  }

  async function handleResume() {
    setActioning(true)
    try { await resumeAnalysis(id); await refresh() } catch (err) { alert(err.message) }
    setActioning(false)
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
            <h1 className="text-xl font-bold text-slate-900">Analysis Detail</h1>
            <p className="text-xs text-slate-400 mt-1 font-mono">{analysis.analysis_id}</p>
            <p className="text-xs text-slate-400">{new Date(analysis.created_at).toLocaleString()}</p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <Badge status={analysis.status} />
            {analysis.gap_count != null && (
              <span className={`text-sm font-bold rounded-full px-3 py-0.5 ${
                analysis.gap_count > 0 ? 'bg-red-100 text-red-700' : 'bg-emerald-100 text-emerald-700'
              }`}>
                {analysis.gap_count} gap{analysis.gap_count !== 1 ? 's' : ''}
              </span>
            )}
            {isActive && (
              <button
                onClick={handlePause}
                disabled={actioning}
                className="flex items-center gap-1.5 rounded-lg border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-700 hover:bg-amber-100 disabled:opacity-60 transition-colors"
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
                className="flex items-center gap-1.5 rounded-lg border border-brand-300 bg-brand-50 px-3 py-1.5 text-xs font-semibold text-brand-700 hover:bg-brand-100 disabled:opacity-60 transition-colors"
              >
                {actioning && <Spinner size="sm" />}
                <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                Resume
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Live progress */}
      {isActive && <ProgressPanel analysisId={id} currentClauseId={analysis.current_clause_id} initialGapCount={analysis.gap_count ?? 0} onClauseComplete={handleClauseComplete} onAnalysisDone={handleAnalysisDone} />}

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
