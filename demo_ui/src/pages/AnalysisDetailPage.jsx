import { useEffect, useState, useRef, useMemo } from 'react'
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

// ── Live Progress Panel ──────────────────────────────────────────────────────
function ProgressPanel({ analysisId }) {
  const { messages, isConnected } = useJobProgress(analysisId)
  const bottomRef = useRef()
  const [fetchedCompleted, setFetchedCompleted] = useState(0)

  // Seed the initial completed count from persisted results so a page reload
  // shows the correct number immediately, before any WS event arrives.
  useEffect(() => {
    getResults(analysisId)
      .then(r => setFetchedCompleted((r || []).length))
      .catch(() => {})
  }, [analysisId])

  const { completed: wsCompleted, total, gapCount, thinkingClause, thinkingText, clauseLog } = useMemo(() => {
    let completed = 0, total = 32, gapCount = 0, thinkingClause = null, thinkingText = ''
    const clauseLog = []
    for (const m of messages) {
      if (m.completed != null) completed = m.completed
      if (m.total != null) total = m.total
      if (m.gap_count != null) gapCount = m.gap_count
      if (m.stage === 'thinking') {
        thinkingClause = m.clause_id || null
        thinkingText = ''               // new clause — reset terminal
      } else if (m.stage === 'thinking_token') {
        thinkingText += m.detail        // accumulate reasoning text
        if (!thinkingClause && m.clause_id) thinkingClause = m.clause_id  // recover on reload
      } else if (m.stage === 'clause') {
        thinkingClause = null
        thinkingText = ''
        if (m.clause_id) clauseLog.push({ clause_id: m.clause_id, decision: m.decision || '' })
      }
    }
    return { completed, total, gapCount, thinkingClause, thinkingText, clauseLog }
  }, [messages])

  // WS events are authoritative once they arrive; fetchedCompleted is the floor
  // so the counter never shows 0 on a fresh page load for a running analysis.
  const completed = Math.max(wsCompleted, fetchedCompleted)

  const terminalRef = useRef()
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight
    }
  }, [thinkingText])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [clauseLog.length])

  const decisionStyle = (d) => {
    if (d === 'Met') return 'text-green-700 bg-green-50 border-green-100'
    if (d === 'Insufficient Evidence') return 'text-yellow-700 bg-yellow-50 border-yellow-100'
    return 'text-red-700 bg-red-50 border-red-100'
  }

  return (
    <div className="rounded-xl border border-blue-100 bg-blue-50 p-4 space-y-3">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isConnected
            ? <Spinner size="sm" />
            : <span className="text-yellow-500 text-xs">⚡ Reconnecting…</span>}
          <span className="text-sm font-semibold text-blue-800">
            Live Progress — {completed}/{total} clauses
          </span>
        </div>
        {gapCount > 0 && (
          <span className="text-xs font-semibold text-red-600 bg-red-50 border border-red-100 rounded-full px-2 py-0.5">
            {gapCount} gap{gapCount !== 1 ? 's' : ''} found
          </span>
        )}
      </div>

      {/* Progress bar */}
      <div className="h-2 rounded-full bg-blue-100">
        <div
          className="h-2 rounded-full bg-blue-500 transition-all duration-500"
          style={{ width: `${Math.min((completed / total) * 100, 100)}%` }}
        />
      </div>

      {/* Thinking terminal — shows live LLM reasoning stream */}
      {(thinkingClause || thinkingText) && (
        <div className="rounded-lg bg-gray-950 border border-gray-800 overflow-hidden">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-900 border-b border-gray-800">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500 opacity-70" />
            <span className="w-2.5 h-2.5 rounded-full bg-yellow-500 opacity-70" />
            <span className="w-2.5 h-2.5 rounded-full bg-green-500 opacity-70" />
            <span className="text-xs text-gray-400 ml-1 font-mono">
              🔍 reasoning — clause {thinkingClause}
            </span>
          </div>
          <div
            ref={terminalRef}
            className="px-3 py-2 font-mono text-xs text-green-400 leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto scrollbar-thin"
          >
            {thinkingText || <span className="animate-pulse">▋</span>}
          </div>
        </div>
      )}

      {/* Clause decision log */}
      <div className="max-h-44 overflow-y-auto space-y-1 scrollbar-thin">
        {clauseLog.length === 0 && !thinkingClause && (
          <p className="text-xs text-blue-400 pl-1">Waiting for clause results…</p>
        )}
        {clauseLog.map((entry, i) => (
          <div
            key={i}
            className={`flex items-center gap-2 text-xs border rounded px-2 py-1 ${decisionStyle(entry.decision)}`}
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
function GapResultsTab({ analysisId }) {
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(null)

  useEffect(() => {
    getResults(analysisId).then(r => { setResults(r || []); setLoading(false) })
  }, [analysisId])

  if (loading) return <div className="flex justify-center py-10"><Spinner size="lg" /></div>
  if (!results.length) return <p className="text-sm text-gray-400 py-6">No results yet.</p>

  const counts = results.reduce((acc, r) => {
    acc[r.decision] = (acc[r.decision] || 0) + 1; return acc
  }, {})

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className="flex flex-wrap gap-3">
        {Object.entries(counts).map(([d, n]) => (
          <div key={d} className="rounded-lg bg-gray-50 border border-gray-100 px-4 py-2 text-center">
            <div className="text-lg font-bold text-gray-800">{n}</div>
            <div className="text-xs text-gray-500">{d}</div>
          </div>
        ))}
      </div>

      {/* Table */}
      <div className="rounded-xl border border-gray-100 overflow-hidden">
        {results.map(r => (
          <div key={r.clause_id} className="border-b border-gray-50 last:border-0">
            <button
              onClick={() => setExpanded(expanded === r.clause_id ? null : r.clause_id)}
              className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 transition-colors"
            >
              <span className="font-mono text-xs text-gray-500 w-10">{r.clause_id}</span>
              <Badge status={r.decision} />
              <div className="flex-1 ml-1">
                <div className="text-xs text-gray-500">
                  Confidence: {(r.confidence * 100).toFixed(0)}%
                </div>
              </div>
              <span className="text-gray-400 text-xs">{expanded === r.clause_id ? '▲' : '▼'}</span>
            </button>
            {expanded === r.clause_id && (
              <div className="px-4 pb-4 bg-gray-50 space-y-3">
                <div>
                  <p className="text-xs font-semibold text-gray-600 mb-1">Reasoning</p>
                  <p className="text-xs text-gray-700 leading-relaxed">{r.reasoning}</p>
                </div>
                {r.missing_evidence?.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-gray-600 mb-1">Missing Evidence</p>
                    <ul className="list-disc list-inside space-y-0.5">
                      {r.missing_evidence.map((e, i) => (
                        <li key={i} className="text-xs text-red-600">{e}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {r.citations?.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-gray-600 mb-1">Citations</p>
                    <div className="flex flex-wrap gap-2">
                      {r.citations.map((c, i) => (
                        <span key={i} className="text-xs bg-white border border-gray-200 rounded px-2 py-0.5 text-gray-500">
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
function RecommendationsTab({ analysisId }) {
  const [recs, setRecs] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getRecommendations(analysisId).then(r => { setRecs(r || []); setLoading(false) })
  }, [analysisId])

  if (loading) return <div className="flex justify-center py-10"><Spinner size="lg" /></div>
  if (!recs.length) return <p className="text-sm text-gray-400 py-6">No recommendations yet. Run and complete an analysis first.</p>

  const byClause = recs.reduce((acc, r) => {
    ;(acc[r.clause_id] = acc[r.clause_id] || []).push(r); return acc
  }, {})

  function Stars({ n, max = 5, color = 'text-yellow-400' }) {
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
          <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">
            Clause {clauseId}
          </h4>
          <div className="space-y-3">
            {items.map((rec, i) => (
              <div key={i} className="rounded-xl bg-white border border-gray-100 shadow-sm p-4">
                <p className="text-sm text-gray-800 mb-3">{rec.text}</p>
                <div className="flex flex-wrap gap-4 text-xs text-gray-500">
                  <span>Cost: <Stars n={rec.cost} color="text-red-400" /></span>
                  <span>Impact: <Stars n={rec.impact} color="text-brand-500" /></span>
                  <span>Effort: <strong>{rec.effort_weeks}w</strong></span>
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
function MissingRequirementsTab({ analysisId }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [copied, setCopied] = useState(null)

  useEffect(() => {
    getMissingRequirements(analysisId).then(r => { setItems(r || []); setLoading(false) })
  }, [analysisId])

  if (loading) return <div className="flex justify-center py-10"><Spinner size="lg" /></div>
  if (!items.length) return <p className="text-sm text-gray-400 py-6">No missing requirement requests yet.</p>

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
          <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Clause {clauseId}</h4>
          <div className="space-y-3">
            {reqs.map((req, i) => {
              const key = `${clauseId}-${i}`
              return (
                <div key={i} className="rounded-xl bg-white border border-gray-100 shadow-sm p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1">
                      <p className="text-xs text-brand-600 font-mono mb-1">{req.field_path}</p>
                      <p className="text-sm text-gray-700 leading-relaxed">{req.request_text}</p>
                    </div>
                    <button
                      onClick={() => copy(req.request_text, key)}
                      className="flex-shrink-0 text-xs text-gray-400 hover:text-gray-700 border border-gray-200 rounded px-2 py-1"
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

  async function refresh() {
    const a = await getAnalysis(id).catch(() => null)
    setAnalysis(a)
  }

  useEffect(() => {
    refresh().finally(() => setLoading(false))

    // Poll status while active
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
  if (!analysis) return <p className="text-center text-gray-400 py-20">Analysis not found.</p>

  const isActive = ACTIVE.includes(analysis.status)

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Analysis Detail</h1>
          <p className="text-xs text-gray-400 mt-1 font-mono">{analysis.analysis_id}</p>
          <p className="text-xs text-gray-400">{new Date(analysis.created_at).toLocaleString()}</p>
        </div>
        <div className="flex items-center gap-3">
          <Badge status={analysis.status} />
          {analysis.gap_count != null && (
            <span className="text-sm font-semibold text-red-600">{analysis.gap_count} gaps</span>
          )}
          {isActive && (
            <button
              onClick={handlePause}
              disabled={actioning}
              className="flex items-center gap-1 rounded-lg border border-yellow-300 bg-yellow-50 px-3 py-1.5 text-xs font-semibold text-yellow-700 hover:bg-yellow-100 disabled:opacity-60"
            >
              {actioning && <Spinner size="sm" />} ⏸ Pause
            </button>
          )}
          {analysis.status === 'paused' && (
            <button
              onClick={handleResume}
              disabled={actioning}
              className="flex items-center gap-1 rounded-lg border border-brand-300 bg-brand-50 px-3 py-1.5 text-xs font-semibold text-brand-700 hover:bg-brand-100 disabled:opacity-60"
            >
              {actioning && <Spinner size="sm" />} ▶ Resume
            </button>
          )}
        </div>
      </div>

      {/* Live progress */}
      {isActive && <ProgressPanel analysisId={id} />}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200">
        {[
          ['results', '📊 Gap Results'],
          ['recommendations', '💡 Recommendations'],
          ['missing', '📋 Missing Requirements'],
        ].map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === key
                ? 'border-brand-600 text-brand-700'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="rounded-xl bg-white border border-gray-100 shadow-sm p-5">
        {tab === 'results'          && <GapResultsTab analysisId={id} />}
        {tab === 'recommendations'  && <RecommendationsTab analysisId={id} />}
        {tab === 'missing'          && <MissingRequirementsTab analysisId={id} />}
      </div>
    </div>
  )
}
