import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { listAnalyses, getResults, getStaleness, reanalyzeDelta } from '../api/analyses.js'
import { listDocuments } from '../api/documents.js'
import Badge from '../components/Badge.jsx'
import Spinner from '../components/Spinner.jsx'
import StalenessBanner from '../components/StalenessBanner.jsx'

/* ── Stat Card ──────────────────────────────────── */
function StatCard({ icon, label, value, sub, to, color, delay }) {
  const colorMap = {
    violet: { box: 'bg-violet-50 border-violet-100', icon: 'text-violet-600' },
    sky:    { box: 'bg-sky-50 border-sky-100',       icon: 'text-sky-600' },
    brand:  { box: 'bg-brand-50 border-brand-100',   icon: 'text-brand-600' },
  }
  const c = colorMap[color] || colorMap.brand

  const inner = (
    <div
      className="h-full rounded-2xl bg-white/80 backdrop-blur-sm border border-gray-200/60 shadow-sm p-5 hover:shadow-lg hover:-translate-y-0.5 transition-all duration-300 group animate-fade-in-up"
      style={{ animationDelay: `${delay || 0}ms` }}
    >
      <div className="flex items-start justify-between mb-4">
        <div className={`rounded-xl p-2.5 border ${c.box}`}>
          <span className={c.icon}>{icon}</span>
        </div>
        <span className="text-xs font-semibold text-slate-400 uppercase tracking-wide text-right leading-tight max-w-[100px]">{label}</span>
      </div>
      <div className="text-3xl font-bold text-slate-900">{value}</div>
      {sub && <div className="mt-1.5 text-xs text-slate-400">{sub}</div>}
    </div>
  )
  return to ? <Link to={to}>{inner}</Link> : inner
}

// SVG Icons
const DocsIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
  </svg>
)
const AnalysisIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
  </svg>
)
const StartIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
    <path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
)
const UploadIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
  </svg>
)
const ChatIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
  </svg>
)
const ComplianceIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M12 3l7.5 3v5.25c0 4.65-3.2 8.38-7.5 9.75-4.3-1.37-7.5-5.1-7.5-9.75V6L12 3z" />
  </svg>
)

const QUICK_ACTIONS = [
  { to: '/analyses', label: 'Start analysis', hint: 'Run a gap assessment', icon: <StartIcon />, color: 'text-emerald-600 bg-emerald-50 dark:bg-emerald-950/60 dark:text-emerald-300' },
  { to: '/documents', label: 'Upload document', hint: 'Add compliance evidence', icon: <UploadIcon />, color: 'text-sky-600 bg-sky-50 dark:bg-sky-950/60 dark:text-sky-300' },
  { to: '/chat', label: 'Ask VerdeAI', hint: 'Explore your gaps', icon: <ChatIcon />, color: 'text-violet-600 bg-violet-50 dark:bg-violet-950/60 dark:text-violet-300' },
]

function QuickActionsCard() {
  return (
    <div className="h-full rounded-2xl border border-gray-200/60 bg-white/80 p-4 shadow-sm backdrop-blur-sm animate-fade-in-up dark:border-slate-700 dark:bg-slate-900/80" style={{ animationDelay: '240ms' }}>
      <p className="px-2 pb-3 pt-1 text-xs font-semibold uppercase tracking-wider text-slate-400">Quick actions</p>
      <div className="space-y-2">
        {QUICK_ACTIONS.map(action => (
          <Link key={action.to} to={action.to} className="group flex min-h-16 items-center gap-3 rounded-xl border border-transparent px-3 py-2.5 transition-all hover:border-slate-200 hover:bg-slate-50 dark:hover:border-slate-700 dark:hover:bg-slate-800">
            <span className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl ${action.color}`}>{action.icon}</span>
            <span className="min-w-0">
              <span className="block truncate text-sm font-semibold text-slate-700 dark:text-slate-200">{action.label}</span>
              <span className="mt-0.5 block truncate text-xs text-slate-400">{action.hint}</span>
            </span>
            <svg aria-hidden="true" className="ml-auto h-3.5 w-3.5 flex-shrink-0 text-slate-300 transition-transform group-hover:translate-x-0.5 group-hover:text-brand-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="m9 18 6-6-6-6" /></svg>
          </Link>
        ))}
      </div>
    </div>
  )
}

export default function Dashboard() {
  const [analyses, setAnalyses] = useState([])
  const [docs, setDocs] = useState([])
  const [latestResults, setLatestResults] = useState(null)
  const [staleness, setStaleness] = useState(null)
  const [reanalyzing, setReanalyzing] = useState(false)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    Promise.all([
      listAnalyses().catch(() => []),
      listDocuments().catch(() => []),
    ]).then(([a, d]) => {
      setAnalyses(a || [])
      const allDocs = Array.isArray(d) ? d : d?.items || []
      setDocs(allDocs.filter(doc => doc.status !== 'deleted'))
      setLoading(false)
    })
  }, [])

  const latest = analyses[0] || null

  // Fetch clause-level results for the latest completed analysis, to show
  // a met/partially-met/not-met breakdown instead of just the gap count.
  useEffect(() => {
    if (latest?.status === 'complete') {
      getResults(latest.analysis_id).then(setLatestResults).catch(() => setLatestResults(null))
    } else {
      setLatestResults(null)
    }
  }, [latest?.analysis_id, latest?.status])
  // Check whether the latest analysis's evidence has changed since it ran.
  useEffect(() => {
    if (latest?.status !== 'complete') { setStaleness(null); return }
    let cancelled = false
    getStaleness(latest.analysis_id)
      .then(s => { if (!cancelled) setStaleness(s) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [latest?.analysis_id, latest?.status])

  async function handleReanalyze() {
    setReanalyzing(true)
    try {
      const res = await reanalyzeDelta(latest.analysis_id)
      navigate(`/analyses/${latest.profile_id}/${res.analysis_id}`)
    } catch (err) {
      alert(err.message)
      setReanalyzing(false)
    }
  }

  const processedDocs = docs.filter(d => d.status === 'ready').length
  const complianceTotal = latestResults?.length || 0
  const complianceMet = latestResults?.filter(result => result.decision === 'Met').length || 0

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Spinner size="lg" /></div>
  }

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      {/* Page heading */}
      <div className="animate-fade-in-up">
        <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
        <p className="text-sm text-slate-500 mt-1">Welcome to your ISO 14001 compliance workspace</p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard
          icon={<DocsIcon />}
          label="Documents Processed"
          value={processedDocs}
          sub={`of ${docs.length} uploaded`}
          to="/documents"
          color="sky"
          delay={80}
        />
        <StatCard
          icon={<AnalysisIcon />}
          label="Analyses Run"
          value={analyses.length}
          sub={latest ? `Last: ${latest.status}` : 'None yet'}
          to="/analyses"
          color="brand"
          delay={160}
        />
        <StatCard
          icon={<ComplianceIcon />}
          label="Compliance Coverage"
          value={complianceTotal ? `${complianceMet}/${complianceTotal}` : '—'}
          sub={complianceTotal ? 'clauses currently met' : 'Run an analysis to calculate'}
          to={latest ? `/analyses/${latest.profile_id}/${latest.analysis_id}` : '/analyses'}
          color="violet"
          delay={200}
        />
      </div>

      {/* Compliance Score + Latest Analysis */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* Latest analysis */}
        {latest && (
          <div className="rounded-2xl bg-white/80 backdrop-blur-sm border border-gray-200/60 shadow-sm p-6 animate-fade-in-up" style={{ animationDelay: '280ms' }}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-slate-700">Latest Analysis</h3>
              <Badge status={latest.status} />
            </div>
            <p className="text-xs text-slate-400 font-mono mb-3">
              {latest.analysis_id.slice(0, 12)}… · {new Date(latest.created_at).toLocaleString()}
            </p>
            {latest.status === 'complete' && staleness?.stale && (
              <div className="mb-4">
                <StalenessBanner staleness={staleness} onReanalyze={handleReanalyze} reanalyzing={reanalyzing} />
              </div>
            )}
            {latestResults && latestResults.length > 0 ? (() => {
              const total = latestResults.length
              const counts = latestResults.reduce((acc, r) => { acc[r.decision] = (acc[r.decision] || 0) + 1; return acc }, {})
              const met = counts['Met'] || 0
              const partial = counts['Partially Met'] || 0
              const notMet = counts['Not Met'] || 0
              const other = total - met - partial - notMet
              const pctOf = (n) => total ? (n / total) * 100 : 0
              return (
                <div className="mb-4">
                  <div className="flex items-baseline gap-2 mb-2">
                    <span className="text-3xl font-bold text-slate-900">{met}</span>
                    <span className="text-sm text-slate-400">of {total} clauses met</span>
                  </div>
                  <div className="flex h-2.5 rounded-full overflow-hidden bg-gray-100">
                    {met > 0 && <div className="bg-emerald-500" style={{ width: `${pctOf(met)}%` }} />}
                    {partial > 0 && <div className="bg-amber-400" style={{ width: `${pctOf(partial)}%` }} />}
                    {notMet > 0 && <div className="bg-red-500" style={{ width: `${pctOf(notMet)}%` }} />}
                    {other > 0 && <div className="bg-slate-300" style={{ width: `${pctOf(other)}%` }} />}
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2.5 text-xs text-slate-500">
                    <span className="inline-flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-emerald-500" />{met} Met</span>
                    <span className="inline-flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-amber-400" />{partial} Partially Met</span>
                    <span className="inline-flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-red-500" />{notMet} Not Met</span>
                    {other > 0 && <span className="inline-flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-slate-300" />{other} Other</span>}
                  </div>
                </div>
              )
            })() : latest.gap_count != null && (
              <p className="text-sm text-slate-600 mb-4">
                <span className="text-3xl font-bold text-red-500">{latest.gap_count}</span>
                <span className="ml-2 text-slate-400">gaps identified</span>
              </p>
            )}
            <Link
              to={`/analyses/${latest.profile_id}/${latest.analysis_id}`}
              className="inline-flex items-center gap-1.5 text-sm font-semibold text-brand-600 hover:text-brand-700 transition-colors"
            >
              View Full Report
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
            </Link>
          </div>
        )}
        <QuickActionsCard />
      </div>

    </div>
  )
}
