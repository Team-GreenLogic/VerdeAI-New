import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getCompleteness } from '../api/orgProfile.js'
import { listAnalyses, createAnalysis } from '../api/analyses.js'
import { listDocuments } from '../api/documents.js'
import Badge from '../components/Badge.jsx'
import Spinner from '../components/Spinner.jsx'

function StatCard({ icon, label, value, sub, to, color }) {
  const colorMap = {
    violet: { box: 'bg-violet-50', icon: 'text-violet-600' },
    sky:    { box: 'bg-sky-50',    icon: 'text-sky-600' },
    brand:  { box: 'bg-brand-50',  icon: 'text-brand-600' },
  }
  const c = colorMap[color] || colorMap.brand

  const inner = (
    <div className="rounded-xl bg-white border border-slate-200 shadow-sm p-5 hover:shadow-md transition-shadow group">
      <div className="flex items-start justify-between mb-4">
        <div className={`rounded-lg p-2.5 ${c.box}`}>
          <span className={c.icon}>{icon}</span>
        </div>
        <span className="text-xs font-semibold text-slate-400 uppercase tracking-wide text-right leading-tight max-w-[100px]">{label}</span>
      </div>
      <div className="text-3xl font-bold text-slate-900">{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-400">{sub}</div>}
    </div>
  )
  return to ? <Link to={to}>{inner}</Link> : inner
}

// SVG Icons
const ProfileIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
  </svg>
)
const DocsIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
  </svg>
)
const AnalysisIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
  </svg>
)
const StartIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
    <path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
)
const UploadIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
  </svg>
)
const ChatIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
  </svg>
)

export default function Dashboard() {
  const [completeness, setCompleteness] = useState(null)
  const [analyses, setAnalyses] = useState([])
  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(true)
  const [starting, setStarting] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    Promise.all([
      getCompleteness().catch(() => null),
      listAnalyses().catch(() => []),
      listDocuments().catch(() => []),
    ]).then(([c, a, d]) => {
      setCompleteness(c)
      setAnalyses(a || [])
      setDocs(Array.isArray(d) ? d : d?.items || [])
      setLoading(false)
    })
  }, [])

  const latest = analyses[0] || null
  const activeStatuses = ['pending', 'running']
  const hasActive = analyses.some(a => activeStatuses.includes(a.status))
  const processedDocs = docs.filter(d => d.status === 'completed').length

  async function handleStartAnalysis() {
    setStarting(true)
    try {
      const res = await createAnalysis('full')
      navigate(`/analyses/${res.analysis_id}`)
    } catch (err) {
      alert(err.message)
    } finally {
      setStarting(false)
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64"><Spinner size="lg" /></div>
  }

  const pct = completeness?.overall_pct ?? 0
  const latestStatusColor = latest ? {
    complete: 'emerald', failed: 'red', paused: 'amber', running: 'blue', pending: 'slate'
  }[latest.status] || 'slate' : 'slate'

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Page heading */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
        <p className="text-sm text-slate-500 mt-1">Welcome to your ISO 14001 compliance workspace</p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          icon={<ProfileIcon />}
          label="Profile Completeness"
          value={`${pct}%`}
          sub="across all 32 clauses"
          to="/org-profile"
          color="violet"
        />
        <StatCard
          icon={<DocsIcon />}
          label="Documents Processed"
          value={processedDocs}
          sub={`of ${docs.length} uploaded`}
          to="/documents"
          color="sky"
        />
        <StatCard
          icon={<AnalysisIcon />}
          label="Analyses Run"
          value={analyses.length}
          sub={latest ? `Last: ${latest.status}` : 'None yet'}
          to="/analyses"
          color="brand"
        />
      </div>

      {/* Completeness progress */}
      {completeness && (
        <div className="rounded-xl bg-white border border-slate-200 border-l-4 border-l-brand-500 shadow-sm p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold text-slate-700">Org Profile Completeness</span>
            <span className="text-sm font-bold text-brand-600">{pct}%</span>
          </div>
          <div className="h-3 rounded-full bg-slate-100 overflow-hidden">
            <div
              className="h-3 rounded-full bg-gradient-to-r from-brand-400 to-brand-600 transition-all"
              style={{ width: `${pct}%` }}
            />
          </div>
          <p className="mt-2 text-xs text-slate-400">
            {completeness.clauses_filled ?? 0} of 32 clauses documented.{' '}
            <Link to="/org-profile" className="text-brand-600 hover:underline font-medium">Complete your profile →</Link>
          </p>
        </div>
      )}

      {/* Latest analysis */}
      {latest && (
        <div className={`rounded-xl bg-white border border-slate-200 border-l-4 border-l-${latestStatusColor}-500 shadow-sm p-5`}>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-semibold text-slate-700">Latest Analysis</span>
            <Badge status={latest.status} />
          </div>
          <p className="text-xs text-slate-400 font-mono mb-3">
            {latest.analysis_id} · {new Date(latest.created_at).toLocaleString()}
          </p>
          {latest.gap_count != null && (
            <p className="text-sm text-slate-600 mb-3">
              <span className="text-2xl font-bold text-red-600">{latest.gap_count}</span>
              <span className="ml-1 text-slate-500">gaps identified</span>
            </p>
          )}
          <Link
            to={`/analyses/${latest.analysis_id}`}
            className="inline-flex items-center gap-1 text-sm font-semibold text-brand-600 hover:text-brand-700"
          >
            View Full Report →
          </Link>
        </div>
      )}

      {/* Quick actions */}
      <div>
        <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Quick Actions</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <button
            onClick={handleStartAnalysis}
            disabled={hasActive || starting || processedDocs === 0}
            className="flex flex-col items-center gap-3 rounded-xl bg-brand-600 hover:bg-brand-700 text-white p-5 text-center disabled:opacity-50 transition-colors"
            title={processedDocs === 0 ? 'Upload documents first' : hasActive ? 'An analysis is already running' : ''}
          >
            <span className="flex items-center justify-center w-10 h-10 rounded-full bg-white/20">
              {starting ? <Spinner size="sm" className="border-white/30 border-t-white" /> : <StartIcon />}
            </span>
            <div>
              <p className="text-sm font-semibold">Start Full Analysis</p>
              <p className="text-xs text-brand-100 mt-0.5">Run ISO 14001 gap analysis</p>
            </div>
          </button>

          <Link
            to="/documents"
            className="flex flex-col items-center gap-3 rounded-xl border-2 border-dashed border-slate-200 hover:border-brand-400 hover:bg-brand-50 p-5 text-center transition-all"
          >
            <span className="flex items-center justify-center w-10 h-10 rounded-full bg-sky-50 text-sky-600">
              <UploadIcon />
            </span>
            <div>
              <p className="text-sm font-semibold text-slate-700">Upload Document</p>
              <p className="text-xs text-slate-400 mt-0.5">Add compliance evidence</p>
            </div>
          </Link>

          <Link
            to="/chat"
            className="flex flex-col items-center gap-3 rounded-xl border-2 border-dashed border-slate-200 hover:border-brand-400 hover:bg-brand-50 p-5 text-center transition-all"
          >
            <span className="flex items-center justify-center w-10 h-10 rounded-full bg-violet-50 text-violet-600">
              <ChatIcon />
            </span>
            <div>
              <p className="text-sm font-semibold text-slate-700">Ask a Question</p>
              <p className="text-xs text-slate-400 mt-0.5">Chat with your documents</p>
            </div>
          </Link>
        </div>
      </div>
    </div>
  )
}
