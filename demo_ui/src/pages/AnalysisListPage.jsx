import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { listAnalyses, createAnalysis } from '../api/analyses.js'
import Badge from '../components/Badge.jsx'
import Spinner from '../components/Spinner.jsx'

export default function AnalysisListPage() {
  const [analyses, setAnalyses] = useState([])
  const [loading, setLoading] = useState(true)
  const [starting, setStarting] = useState(false)
  const navigate = useNavigate()

  async function refresh() {
    const data = await listAnalyses().catch(() => [])
    setAnalyses(data || [])
  }

  useEffect(() => {
    refresh().finally(() => setLoading(false))
  }, [])

  const activeStatuses = ['pending', 'running']
  const hasActive = analyses.some(a => activeStatuses.includes(a.status))

  async function handleStart() {
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

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Gap Analysis</h1>
          <p className="text-sm text-gray-500 mt-1">Run ISO 14001 compliance gap analyses against your documents.</p>
        </div>
        <button
          onClick={handleStart}
          disabled={hasActive || starting}
          title={hasActive ? 'An analysis is already running' : ''}
          className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50 transition-colors"
        >
          {starting && <Spinner size="sm" />}
          🔍 Start Full Analysis
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-10"><Spinner size="lg" /></div>
      ) : analyses.length === 0 ? (
        <div className="rounded-xl bg-white border border-gray-100 p-12 text-center text-gray-400">
          <p className="text-4xl mb-3">🔍</p>
          <p className="text-sm font-medium">No analyses yet.</p>
          <p className="text-xs mt-1">Click "Start Full Analysis" to begin your first compliance check.</p>
        </div>
      ) : (
        <div className="rounded-xl bg-white border border-gray-100 shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Analysis ID</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Status</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Gaps</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Scope</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Date</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {analyses.map(a => (
                <tr key={a.analysis_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs text-gray-600">
                    {a.analysis_id.slice(0, 8)}…
                  </td>
                  <td className="px-4 py-3"><Badge status={a.status} /></td>
                  <td className="px-4 py-3 font-semibold text-gray-800">
                    {a.gap_count ?? '—'}
                  </td>
                  <td className="px-4 py-3 text-gray-500 capitalize">
                    {typeof a.scope === 'string' ? a.scope : 'custom'}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-400">
                    {new Date(a.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      to={`/analyses/${a.analysis_id}`}
                      className="text-xs font-medium text-brand-600 hover:text-brand-700"
                    >
                      View →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
