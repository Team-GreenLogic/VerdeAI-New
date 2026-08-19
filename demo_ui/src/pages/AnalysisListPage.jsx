import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { listAnalyses, createAnalysis, deleteAnalysis, getVersions, getStaleness, reanalyzeDelta } from '../api/analyses.js'
import Badge from '../components/Badge.jsx'
import Spinner from '../components/Spinner.jsx'
import StalenessBanner from '../components/StalenessBanner.jsx'

const DEFAULT_VERSION_ID = 'iso-14001-2015'

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
  const { profileId } = useParams()
  const [analyses, setAnalyses] = useState([])
  const [versions, setVersions] = useState([])
  const [selectedVersion, setSelectedVersion] = useState(DEFAULT_VERSION_ID)
  const [loading, setLoading] = useState(true)
  const [starting, setStarting] = useState(false)
  const [deletingId, setDeletingId] = useState(null)
  const [staleness, setStaleness] = useState(null)
  const [reanalyzing, setReanalyzing] = useState(false)
  const navigate = useNavigate()

  async function refresh() {
    const [data, vdata] = await Promise.all([
      listAnalyses(profileId).catch(() => []),
      getVersions().catch(() => []),
    ])
    setAnalyses(data || [])
    const vlist = vdata || []
    setVersions(vlist)
    if (vlist.length > 0 && !vlist.find(v => v.version_id === selectedVersion)) {
      setSelectedVersion(vlist[0].version_id)
    }
  }

  async function handleDelete(analysisId, e) {
    e.preventDefault()
    e.stopPropagation()
    if (!window.confirm('Are you sure you want to delete this analysis report? This action cannot be undone.')) {
      return
    }
    setDeletingId(analysisId)
    try {
      await deleteAnalysis(analysisId)
      setAnalyses(prev => prev.filter(a => a.analysis_id !== analysisId))
    } catch (err) {
      alert(err.message || 'Failed to delete analysis')
    } finally {
      setDeletingId(null)
    }
  }

  useEffect(() => {
    refresh().finally(() => setLoading(false))
  }, [profileId])

  const activeStatuses = ['pending', 'running']
  const hasActive = analyses.some(a => activeStatuses.includes(a.status))
  const chosenVersion = versions.find(v => v.version_id === selectedVersion)
  const latest = analyses[0] || null

  // Check whether the newest analysis's evidence has changed since it ran.
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
      navigate(`/analyses/${profileId}/${res.analysis_id}`)
    } catch (err) {
      alert(err.message)
      setReanalyzing(false)
    }
  }

  async function handleStart() {
    setStarting(true)
    try {
      const res = await createAnalysis(profileId, 'full', selectedVersion)
      navigate(`/analyses/${profileId}/${res.analysis_id}`)
    } catch (err) {
      alert(err.message)
    } finally {
      setStarting(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      {/* Header */}
      <div className="rounded-xl bg-white border border-slate-200 border-l-4 border-l-brand-500 shadow-sm p-5">
        <button onClick={() => navigate('/analyses')} className="text-xs text-slate-400 hover:text-brand-600 mb-1 transition-colors">
          ← Analyses
        </button>
        <h1 className="text-xl font-bold text-slate-900">Gap Analysis</h1>
        <p className="text-sm text-slate-500 mt-0.5">Run ISO 14001 compliance gap analyses against your uploaded documents.</p>
      </div>

      {/* Version selection + start action */}
      <div className="rounded-xl bg-white border border-slate-200 shadow-sm p-5 space-y-4">
        <div>
          <h2 className="text-sm font-bold text-slate-800">Select ISO Standard Version</h2>
          <p className="text-xs text-slate-500 mt-0.5">Your company documents will be assessed against the clauses in the selected version.</p>
        </div>

        {versions.length === 0 ? (
          <div className="rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-xs text-amber-800">
            No published ISO versions available. Ask your admin to publish a version before running an analysis.
          </div>
        ) : versions.length <= 4 ? (
          /* Card picker — works well for up to 4 versions */
          <div className={`grid gap-3 ${versions.length === 1 ? 'grid-cols-1 max-w-sm' : 'grid-cols-1 sm:grid-cols-2'}`}>
            {versions.map(v => {
              const isSelected = v.version_id === selectedVersion
              return (
                <button
                  key={v.version_id}
                  onClick={() => !hasActive && !starting && setSelectedVersion(v.version_id)}
                  disabled={hasActive || starting}
                  className={`text-left rounded-xl border-2 p-4 transition-all disabled:cursor-not-allowed ${
                    isSelected
                      ? 'border-brand-500 bg-brand-50 shadow-sm'
                      : 'border-slate-200 hover:border-brand-300 hover:bg-slate-50'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className={`text-sm font-bold truncate ${isSelected ? 'text-brand-700' : 'text-slate-800'}`}>
                        {v.name}
                      </p>
                      {v.description && (
                        <p className="text-xs text-slate-500 mt-0.5 line-clamp-2">{v.description}</p>
                      )}
                    </div>
                    <div className={`w-4 h-4 rounded-full border-2 flex-shrink-0 mt-0.5 ${
                      isSelected ? 'border-brand-500 bg-brand-500' : 'border-slate-300'
                    }`}>
                      {isSelected && (
                        <svg className="w-full h-full text-white" fill="currentColor" viewBox="0 0 24 24">
                          <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"/>
                        </svg>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-3 mt-3">
                    <span className="text-[10px] font-mono bg-white border border-slate-200 text-slate-500 rounded px-1.5 py-0.5">
                      {v.version_id}
                    </span>
                    {v.clause_count > 0 && (
                      <span className={`text-[10px] font-semibold rounded-full px-2 py-0.5 ${
                        isSelected ? 'bg-brand-100 text-brand-700' : 'bg-slate-100 text-slate-500'
                      }`}>
                        {v.clause_count} clauses
                      </span>
                    )}
                  </div>
                </button>
              )
            })}
          </div>
        ) : (
          /* Dropdown + detail panel — for 5+ versions */
          <div className="space-y-3">
            <select
              value={selectedVersion}
              onChange={e => setSelectedVersion(e.target.value)}
              disabled={hasActive || starting}
              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-brand-400 disabled:opacity-50"
            >
              {versions.map(v => (
                <option key={v.version_id} value={v.version_id}>{v.name}</option>
              ))}
            </select>
            {chosenVersion && (
              <div className="rounded-lg bg-brand-50 border border-brand-200 px-4 py-3 flex items-center gap-4">
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-bold text-brand-800">{chosenVersion.name}</p>
                  {chosenVersion.description && (
                    <p className="text-xs text-brand-700 mt-0.5">{chosenVersion.description}</p>
                  )}
                </div>
                <div className="flex-shrink-0 text-right">
                  {chosenVersion.clause_count > 0 && (
                    <span className="text-xs font-semibold text-brand-700 bg-brand-100 rounded-full px-2.5 py-1">
                      {chosenVersion.clause_count} clauses
                    </span>
                  )}
                  <p className="text-[10px] font-mono text-brand-500 mt-1">{chosenVersion.version_id}</p>
                </div>
              </div>
            )}
          </div>
        )}

        {versions.length > 0 && (
          <div className="flex items-center justify-between pt-1 border-t border-slate-100">
            <p className="text-xs text-slate-500">
              {chosenVersion
                ? <>Analysing against <strong className="text-slate-700">{chosenVersion.name}</strong> · {chosenVersion.clause_count} clauses</>
                : 'Select a version above'}
            </p>
            <button
              onClick={handleStart}
              disabled={hasActive || starting || !selectedVersion}
              title={hasActive ? 'An analysis is already running — wait for it to complete first' : ''}
              className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50 transition-colors"
            >
              {starting ? <Spinner size="sm" /> : <StartSVG />}
              {hasActive ? 'Analysis running…' : 'Start Full Analysis'}
            </button>
          </div>
        )}
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
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Version</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Date</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {analyses.map((a, idx) => (
                <tr key={a.analysis_id} className="hover:bg-brand-50/40 transition-colors">
                  <td className="px-4 py-3">
                    <span className="font-mono text-xs bg-slate-100 text-slate-600 rounded px-1.5 py-0.5">
                      {a.analysis_id.slice(0, 8)}…
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Badge status={a.status} />
                      {idx === 0 && (
                        <StalenessBanner staleness={staleness} onReanalyze={handleReanalyze} reanalyzing={reanalyzing} variant="compact" />
                      )}
                    </div>
                  </td>
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
                  <td className="px-4 py-3">
                    <span className="font-mono text-[10px] bg-slate-100 text-slate-500 rounded px-1.5 py-0.5">
                      {a.version_id ?? DEFAULT_VERSION_ID}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-400">
                    {new Date(a.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Link
                        to={`/analyses/${profileId}/${a.analysis_id}`}
                        className="inline-flex items-center gap-1 text-xs font-semibold text-brand-600 hover:text-brand-700 bg-brand-50 hover:bg-brand-100 rounded-md px-2.5 py-1.5 transition-colors"
                      >
                        View →
                      </Link>
                      <button
                        onClick={(e) => handleDelete(a.analysis_id, e)}
                        disabled={deletingId === a.analysis_id}
                        title="Delete this analysis report"
                        className="p-1.5 rounded-md text-slate-400 hover:text-red-600 hover:bg-red-50 disabled:opacity-40 transition-colors cursor-pointer"
                      >
                        {deletingId === a.analysis_id ? (
                          <Spinner size="sm" />
                        ) : (
                          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        )}
                      </button>
                    </div>
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
