import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import Badge from '../components/Badge.jsx'
import Spinner from '../components/Spinner.jsx'
import StalenessBanner from '../components/StalenessBanner.jsx'
import { useJobProgress } from '../hooks/useJobProgress.js'
import {
  createPersonalizedRun,
  getPersonalizedRun,
  getRecommendationContext,
  listPersonalizedRuns,
} from '../api/personalizedRecommendations.js'

const ACTIVE = new Set(['queued', 'researching', 'synthesizing'])

function formatDate(value) {
  if (!value) return '—'
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

function Warning({ title, children, action }) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950/40 sm:flex-row sm:items-center">
      <div className="flex-1">
        <p className="text-sm font-semibold text-amber-900 dark:text-amber-200">{title}</p>
        <div className="mt-0.5 text-xs text-amber-800 dark:text-amber-300">{children}</div>
      </div>
      {action}
    </div>
  )
}

function SourceIcon({ source }) {
  const [failed, setFailed] = useState(false)
  if (failed || !source.favicon_url) {
    return <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-100 text-slate-500">◎</span>
  }
  return <img src={source.favicon_url} alt="" onError={() => setFailed(true)} className="h-9 w-9 rounded-lg border border-slate-200 bg-white object-contain p-1" />
}

function SourcesPanel({ sources = [] }) {
  if (!sources.length) return null
  const retained = sources.filter(source => source.status === 'retained')
  const sourceMix = Object.entries(retained.reduce((counts, source) => {
    const type = source.source_type || 'other'
    counts[type] = (counts[type] || 0) + 1
    return counts
  }, {}))
  const statusStyle = {
    retained: 'bg-emerald-100 text-emerald-700',
    rejected: 'bg-slate-100 text-slate-500',
    visiting: 'bg-blue-100 text-blue-700',
    skipped: 'bg-amber-100 text-amber-700',
    replaced: 'bg-cyan-100 text-cyan-700',
    failed: 'bg-red-100 text-red-700',
  }
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div><h2 className="text-sm font-bold text-slate-800">Explored sources</h2><p className="text-xs text-slate-500">Sites evaluated against the anonymous peer context.</p></div>
        <span className="text-xs font-semibold text-slate-500">{retained.length} retained</span>
      </div>
      {!!sourceMix.length && <div className="mb-4 flex flex-wrap gap-2">{sourceMix.map(([type, count]) => <span key={type} className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-semibold capitalize text-slate-600">{type.replaceAll('_', ' ')} · {count}</span>)}</div>}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {sources.map(source => {
          const replacement = sources.find(candidate => candidate.replacement_for_source_id === source.source_id && candidate.status === 'retained')
          const displayStatus = source.status === 'skipped' && replacement ? 'replaced' : source.status
          const reason = displayStatus === 'replaced'
            ? `PDF was unavailable; retained HTML alternative from ${replacement.domain}.`
            : source.summary || source.relevance_reason
          return (
          <a key={source.source_id || source.url} href={source.url} target="_blank" rel="noreferrer noopener" className="group rounded-xl border border-slate-200 p-3 transition hover:border-brand-300 hover:shadow-sm">
            <div className="flex gap-3">
              <SourceIcon source={source} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-slate-800 group-hover:text-brand-700">{source.title || source.domain}</p>
                <p className="truncate text-xs text-slate-400">{source.domain}{source.source_type && ` · ${source.source_type.replaceAll('_', ' ')}`}</p>
              </div>
              <span className={`h-fit rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize ${statusStyle[displayStatus] || statusStyle.visiting}`}>{displayStatus}</span>
            </div>
            {reason && <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-slate-500" title={source.failure_detail || undefined}>{reason}</p>}
          </a>
          )
        })}
      </div>
    </section>
  )
}

function ResearchProgress({ run, messages, isConnected }) {
  const latest = messages[messages.length - 1]
  const queryPct = run?.limits?.max_queries ? Math.min(100, ((latest?.queries_used || run.queries_used || 0) / run.limits.max_queries) * 100) : 8
  return (
    <section aria-live="polite" className="rounded-2xl border border-blue-200 bg-gradient-to-br from-white to-blue-50 p-5 shadow-sm dark:border-blue-800 dark:from-slate-900 dark:to-blue-950/30">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3"><Spinner /><div><h2 className="text-sm font-bold text-slate-800">Research in progress</h2><p className="text-xs text-slate-500">{latest?.detail || 'Preparing the research run…'}</p></div></div>
        <span className={`text-xs font-semibold ${isConnected ? 'text-emerald-600' : 'text-amber-600'}`}>{isConnected ? 'Live' : 'Reconnecting…'}</span>
      </div>
      <div className="mt-4 h-2 overflow-hidden rounded-full bg-blue-100"><div className="h-full rounded-full bg-gradient-to-r from-brand-500 to-blue-500 transition-all" style={{ width: `${Math.max(8, queryPct)}%` }} /></div>
      <div className="mt-2 flex justify-between text-[11px] text-slate-400"><span>Iteration {latest?.iteration || run.current_iteration || 1} of {run?.limits?.max_iterations || 3}</span><span>{latest?.queries_used || run.queries_used || 0}/{run?.limits?.max_queries || 8} searches · {latest?.pages_fetched || run.pages_fetched || 0}/{run?.limits?.max_pages || 15} pages</span></div>
      {latest?.query && <p className="mt-2 truncate text-[11px] text-slate-400" title={latest.query}>{latest.query}</p>}
    </section>
  )
}

function RecommendationCard({ recommendation, sourceMap }) {
  return (
    <article className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 bg-slate-50 px-5 py-3">
        <div className="flex flex-wrap items-center gap-2"><span className="rounded bg-slate-200 px-2 py-0.5 font-mono text-xs font-bold text-slate-600">{recommendation.clause_id}</span>{recommendation.limited_web_evidence && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-800">Limited web evidence</span>}</div>
        <p className="mt-2 text-xs text-slate-500"><span className="font-semibold">Original:</span> {recommendation.baseline_text}</p>
      </div>
      <div className="space-y-4 p-5">
        <div><h3 className="text-base font-bold text-slate-900">{recommendation.personalized_text}</h3><p className="mt-1 text-sm leading-relaxed text-slate-600">{recommendation.rationale}</p></div>
        {!!recommendation.action_steps?.length && <div><p className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">Action steps</p><ol className="space-y-2">{recommendation.action_steps.map((step, index) => <li key={index} className="flex gap-2 text-sm text-slate-700"><span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-100 text-[10px] font-bold text-brand-700">{index + 1}</span><span>{step}</span></li>)}</ol></div>}
        {!!recommendation.peer_practices?.length && <div><p className="mb-1 text-xs font-bold uppercase tracking-wide text-slate-500">Comparable practices</p><ul className="list-disc space-y-1 pl-5 text-sm text-slate-600">{recommendation.peer_practices.map((practice, index) => <li key={index}>{practice}</li>)}</ul></div>}
        <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-3 text-xs"><span className="rounded-full bg-slate-100 px-2.5 py-1">Cost {recommendation.cost}</span><span className="rounded-full bg-slate-100 px-2.5 py-1">{recommendation.effort_weeks} weeks</span><span className="rounded-full bg-slate-100 px-2.5 py-1">Impact {recommendation.impact}</span></div>
        {!!recommendation.source_ids?.length && <div className="flex flex-wrap gap-2">{recommendation.source_ids.map(sourceId => { const source = sourceMap[sourceId]; return source ? <a key={sourceId} href={source.url} target="_blank" rel="noreferrer noopener" className="rounded-full border border-brand-200 bg-brand-50 px-2.5 py-1 text-xs font-semibold text-brand-700 hover:bg-brand-100">{source.title || source.domain} ↗</a> : null })}</div>}
      </div>
    </article>
  )
}

export default function RecommendationsPage() {
  const { profileId } = useParams()
  const navigate = useNavigate()
  const [context, setContext] = useState(null)
  const [runs, setRuns] = useState([])
  const [selectedRun, setSelectedRun] = useState(null)
  const [loading, setLoading] = useState(true)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState('')

  const refresh = useCallback(async (preferredRunId = null) => {
    const [nextContext, nextRuns] = await Promise.all([getRecommendationContext(profileId), listPersonalizedRuns(profileId)])
    setContext(nextContext)
    setRuns(nextRuns || [])
    const availableIds = new Set((nextRuns || []).map(run => run.run_id))
    const selectedId = availableIds.has(selectedRun?.run_id) ? selectedRun.run_id : null
    const id = preferredRunId || nextContext.active_run?.run_id || selectedId || nextRuns?.[0]?.run_id
    if (id) setSelectedRun(await getPersonalizedRun(id))
    else setSelectedRun(null)
  }, [profileId, selectedRun?.run_id])

  useEffect(() => { setLoading(true); refresh().catch(err => setError(err.message)).finally(() => setLoading(false)) }, [profileId])
  const activeRunId = selectedRun && ACTIVE.has(selectedRun.status) ? selectedRun.run_id : null
  const { messages, status: wsStatus, isConnected } = useJobProgress(activeRunId, {})

  useEffect(() => {
    if (!activeRunId || !messages.length) return
    const sourceEvents = messages.filter(message => message.source)
    if (sourceEvents.length) {
      setSelectedRun(previous => {
        const map = new Map((previous?.sources || []).map(source => [source.source_id, source]))
        sourceEvents.forEach(message => map.set(message.source.source_id, message.source))
        return { ...previous, sources: [...map.values()] }
      })
    }
  }, [messages, activeRunId])

  useEffect(() => {
    if (wsStatus === 'done' || wsStatus === 'failed') refresh(activeRunId).catch(() => {})
  }, [wsStatus, activeRunId])

  async function startRun() {
    setStarting(true); setError('')
    try { const created = await createPersonalizedRun(profileId); await refresh(created.run_id) }
    catch (err) { setError(err.message) }
    finally { setStarting(false) }
  }

  async function selectRun(runId) {
    setError('')
    try { setSelectedRun(await getPersonalizedRun(runId)) } catch (err) { setError(err.message) }
  }

  const sourceMap = useMemo(() => Object.fromEntries((selectedRun?.sources || []).map(source => [source.source_id, source])), [selectedRun?.sources])
  if (loading) return <div className="flex justify-center py-20"><Spinner size="lg" /></div>

  const profileName = context?.profile?.org_name || 'Company profile'
  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <header className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:flex-row sm:items-center">
        <div className="flex-1"><button onClick={() => navigate('/recommendations')} className="text-xs text-slate-400 hover:text-brand-600">← Change profile</button><h1 className="mt-1 text-2xl font-bold text-slate-900">Personalized Recommendations</h1><p className="mt-1 text-sm text-slate-500">Web-grounded research for <strong className="text-slate-700">{profileName}</strong></p></div>
        <button onClick={startRun} disabled={!context?.can_generate || starting || ACTIVE.has(selectedRun?.status)} className="inline-flex items-center justify-center gap-2 rounded-xl bg-brand-600 px-5 py-3 text-sm font-bold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50">{starting && <Spinner size="sm" />}{runs.length ? 'Generate another' : 'Generate personalized recommendations'}</button>
      </header>

      {error && <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
      {!context?.profile_complete && <Warning title="Complete the company profile" action={<Link to={`/org-profiles/${profileId}`} className="rounded-lg bg-amber-900 px-3 py-2 text-xs font-semibold text-white">Complete profile</Link>}>Add {context.missing_profile_fields.map(field => field.replace('org_', '').replace('_', ' ')).join(', ')} before starting web research.</Warning>}
      {context?.blocked_reason === 'analysis_required' && <Warning title="A completed analysis is required" action={<Link to={`/analyses/${profileId}`} className="rounded-lg bg-amber-900 px-3 py-2 text-xs font-semibold text-white">Run analysis</Link>}>Complete a gap analysis before generating personalized recommendations.</Warning>}
      {context?.blocked_reason === 'no_actionable_gaps' && <Warning title="No actionable gaps">The latest completed analysis has no recommendations that require personalization.</Warning>}
      {['baseline_recommendations_unavailable', 'baseline_recommendations_processing'].includes(context?.blocked_reason) && <Warning title="Baseline recommendations are not ready">The latest analysis is complete, but its recommendation generation is still processing or unavailable.</Warning>}
      {context?.newer_analysis && <Warning title={`Newer analysis is ${context.newer_analysis.status}`} action={<Link to={`/analyses/${profileId}/${context.newer_analysis.analysis_id}`} className="rounded-lg bg-amber-900 px-3 py-2 text-xs font-semibold text-white">View analysis</Link>}>This page is using the latest completed snapshot from {formatDate(context.latest_analysis?.created_at)}.</Warning>}
      <StalenessBanner staleness={context?.staleness} onReanalyze={() => navigate(`/analyses/${profileId}`)} reanalyzing={false} />

      {runs.length > 0 && <div className="flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-4 sm:flex-row sm:items-center"><label htmlFor="run-history" className="text-xs font-bold uppercase tracking-wide text-slate-500">Research history</label><select id="run-history" value={selectedRun?.run_id || ''} onChange={event => selectRun(event.target.value)} className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm"><option value="" disabled>Select a run</option>{runs.map(run => <option key={run.run_id} value={run.run_id}>{formatDate(run.created_at)} · {run.status}</option>)}</select>{selectedRun && <Badge status={selectedRun.status} />}</div>}

      {selectedRun && ACTIVE.has(selectedRun.status) && <ResearchProgress run={selectedRun} messages={messages} isConnected={isConnected} />}
      {selectedRun?.status === 'failed' && <Warning title="Research run failed">{selectedRun.error || 'OpenSERP or recommendation generation could not complete. Generate another run to retry.'}</Warning>}
      <SourcesPanel sources={selectedRun?.sources || []} />

      {selectedRun?.status === 'complete' && <section className="space-y-4"><div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between"><div><h2 className="text-xl font-bold text-slate-900">Recommendations</h2><p className="text-xs text-slate-500">Based on analysis {selectedRun.analysis_id} · generated {formatDate(selectedRun.completed_at)}</p></div><p className="text-xs text-slate-400">{selectedRun.queries_used} searches · {selectedRun.retained_source_count} retained sources · {selectedRun.termination_reason?.replaceAll('_', ' ')}</p></div>{selectedRun.warnings?.map(warning => <Warning key={warning} title="Evidence note">{warning}</Warning>)}{selectedRun.recommendations?.map(recommendation => <RecommendationCard key={recommendation.recommendation_key} recommendation={recommendation} sourceMap={sourceMap} />)}<p className="pb-4 text-center text-xs text-slate-400">AI-generated compliance guidance should be reviewed by a qualified environmental-management professional.</p></section>}

      {!selectedRun && context?.can_generate && <div className="rounded-2xl border border-dashed border-brand-300 bg-brand-50/50 p-12 text-center"><div className="text-4xl">⌕</div><h2 className="mt-3 text-lg font-bold text-slate-800">Ready to research</h2><p className="mx-auto mt-1 max-w-xl text-sm text-slate-500">We will use the company profile, latest completed gaps, and baseline recommendations to find relevant comparable practices and authoritative sources.</p></div>}
    </div>
  )
}
