import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { listAnalyses, createAnalysis } from '../api/analyses.js'
import Badge from '../components/Badge.jsx'
import Spinner from '../components/Spinner.jsx'

const SearchSVG = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-12 h-12" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 15.803a7.5 7.5 0 0010.607 10.607z" />
  </svg>
)

const StartSVG = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.348a1.125 1.125 0 010 1.971l-11.54 6.347a1.125 1.125 0 01-1.667-.986V5.653z" />
  </svg>
)

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
      {/* Header card */}
      <div className="rounded-xl bg-white border border-slate-200 border-l-4 border-l-brand-500 shadow-sm p-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-slate-900">Gap Analysis</h1>
            <p className="text-sm text-slate-500 mt-0.5">Run ISO 14001 compliance gap analyses against your documents.</p>
          </div>
          <button
            onClick={handleStart}
            disabled={hasActive || starting}
            title={hasActive ? 'An analysis is already running' : ''}
            className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50 transition-colors flex-shrink-0"
          >
            {starting ? <Spinner size="sm" /> : <StartSVG />}
            Start Full Analysis
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-10"><Spinner size="lg" /></div>
      ) : analyses.length === 0 ? (
        <div className="rounded-xl bg-white border border-slate-200 p-12 text-center">
          <div className="flex justify-center text-slate-300 mb-3">
            <SearchSVG />
          </div>
          <p className="text-sm font-semibold text-slate-600">No analyses yet</p>
          <p className="text-xs text-slate-400 mt-1">Click "Start Full Analysis" to begin your first compliance check.</p>
        </div>
      ) : (
        <div className="rounded-xl bg-white border border-slate-200 shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Analysis ID</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Status</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Gaps</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Scope</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Date</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {analyses.map(a => (
                <tr key={a.analysis_id} className="hover:bg-brand-50/40 transition-colors">
                  <td className="px-4 py-3">
                    <span className="font-mono text-xs bg-slate-100 text-slate-600 rounded px-1.5 py-0.5">
                      {a.analysis_id.slice(0, 8)}…
                    </span>
                  </td>
                  <td className="px-4 py-3"><Badge status={a.status} /></td>
                  <td className="px-4 py-3">
                    {a.gap_count != null ? (
                      <span className={`font-bold ${a.gap_count > 0 ? 'text-red-600' : 'text-slate-400'}`}>
                        {a.gap_count}
                      </span>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-500 capitalize">
                    {typeof a.scope === 'string' ? a.scope : 'custom'}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-400">
                    {new Date(a.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      to={`/analyses/${a.analysis_id}`}
                      className="inline-flex items-center gap-1 text-xs font-semibold text-brand-600 hover:text-brand-700 bg-brand-50 hover:bg-brand-100 rounded-md px-2.5 py-1 transition-colors"
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
