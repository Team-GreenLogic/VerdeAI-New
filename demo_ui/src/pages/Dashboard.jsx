import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getCompleteness } from '../api/orgProfile.js'
import { listAnalyses, createAnalysis } from '../api/analyses.js'
import { listDocuments } from '../api/documents.js'
import Badge from '../components/Badge.jsx'
import Spinner from '../components/Spinner.jsx'

function StatCard({ icon, label, value, sub, to }) {
  const inner = (
    <div className="rounded-xl bg-white border border-gray-100 shadow-sm p-5 hover:shadow-md transition-shadow">
      <div className="flex items-center gap-3 mb-3">
        <span className="text-2xl">{icon}</span>
        <span className="text-sm font-medium text-gray-500">{label}</span>
      </div>
      <div className="text-3xl font-bold text-gray-900">{value}</div>
      {sub && <div className="mt-1 text-xs text-gray-400">{sub}</div>}
    </div>
  )
  return to ? <Link to={to}>{inner}</Link> : inner
}

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

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">Welcome to your ISO 14001 compliance workspace</p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          icon="🏢"
          label="Profile Completeness"
          value={`${completeness?.overall_pct ?? 0}%`}
          sub="across all 32 clauses"
          to="/org-profile"
        />
        <StatCard
          icon="📄"
          label="Documents Processed"
          value={processedDocs}
          sub={`of ${docs.length} uploaded`}
          to="/documents"
        />
        <StatCard
          icon="🔍"
          label="Analyses Run"
          value={analyses.length}
          sub={latest ? `Last: ${latest.status}` : 'None yet'}
          to="/analyses"
        />
      </div>

      {/* Completeness bar */}
      {completeness && (
        <div className="rounded-xl bg-white border border-gray-100 shadow-sm p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold text-gray-700">Org Profile Completeness</span>
            <span className="text-sm font-bold text-brand-600">{completeness.overall_pct}%</span>
          </div>
          <div className="h-2 rounded-full bg-gray-100">
            <div
              className="h-2 rounded-full bg-brand-500 transition-all"
              style={{ width: `${completeness.overall_pct}%` }}
            />
          </div>
          <p className="mt-2 text-xs text-gray-400">
            A complete profile improves gap analysis accuracy.{' '}
            <Link to="/org-profile" className="text-brand-600 hover:underline">Complete your profile →</Link>
          </p>
        </div>
      )}

      {/* Latest analysis */}
      {latest && (
        <div className="rounded-xl bg-white border border-gray-100 shadow-sm p-5">
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm font-semibold text-gray-700">Latest Analysis</span>
            <Badge status={latest.status} />
          </div>
          <p className="text-xs text-gray-400 mb-3">
            {latest.analysis_id} · {new Date(latest.created_at).toLocaleString()}
          </p>
          {latest.gap_count != null && (
            <p className="text-sm text-gray-600 mb-3">
              <span className="font-semibold text-red-600">{latest.gap_count}</span> gaps identified
            </p>
          )}
          <Link
            to={`/analyses/${latest.analysis_id}`}
            className="text-sm font-medium text-brand-600 hover:text-brand-700"
          >
            View Results →
          </Link>
        </div>
      )}

      {/* Quick actions */}
      <div className="rounded-xl bg-white border border-gray-100 shadow-sm p-5">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">Quick Actions</h3>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={handleStartAnalysis}
            disabled={hasActive || starting || processedDocs === 0}
            className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50 transition-colors"
            title={processedDocs === 0 ? 'Upload documents first' : hasActive ? 'An analysis is already running' : ''}
          >
            {starting && <Spinner size="sm" />}
            🔍 Start Full Analysis
          </button>
          <Link
            to="/documents"
            className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50 transition-colors"
          >
            📄 Upload Document
          </Link>
          <Link
            to="/chat"
            className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50 transition-colors"
          >
            💬 Ask a Question
          </Link>
        </div>
      </div>
    </div>
  )
}
