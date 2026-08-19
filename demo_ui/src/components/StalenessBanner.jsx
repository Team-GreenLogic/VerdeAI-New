import Spinner from './Spinner.jsx'

/**
 * Warns that a completed analysis's evidence has changed since it ran
 * (new/removed document chunks) and offers to re-run only the affected clauses.
 * Driven by `staleness` from `getStaleness(analysisId)` — renders nothing
 * unless `staleness.stale` is true.
 */
export default function StalenessBanner({ staleness, onReanalyze, reanalyzing, variant = 'full' }) {
  if (!staleness?.stale) return null

  const detail = [
    staleness.new_chunk_count > 0 && `${staleness.new_chunk_count} new document chunk${staleness.new_chunk_count !== 1 ? 's' : ''}`,
    staleness.removed_chunk_count > 0 && `${staleness.removed_chunk_count} removed`,
  ].filter(Boolean).join(', ')

  if (variant === 'compact') {
    return (
      <button
        onClick={onReanalyze}
        disabled={reanalyzing}
        title={`${detail} since this analysis ran. Click to re-analyze the affected clauses.`}
        className="inline-flex items-center gap-1 rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-900 hover:bg-amber-100 dark:border-amber-700 dark:bg-amber-950/60 dark:text-amber-200 dark:hover:bg-amber-900/60 disabled:opacity-60 transition-colors"
      >
        {reanalyzing
          ? <Spinner size="sm" />
          : <svg className="w-3 h-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
            </svg>}
        {reanalyzing ? 'Starting…' : 'Stale'}
      </button>
    )
  }

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 flex items-start gap-3 dark:border-amber-700 dark:bg-amber-950/60">
      <svg className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
      </svg>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-amber-900 dark:text-amber-200">New uploads detected since this analysis</p>
        <p className="text-xs text-amber-800 dark:text-amber-300 mt-0.5">
          {staleness.new_chunk_count > 0 && `${staleness.new_chunk_count} new document chunk${staleness.new_chunk_count !== 1 ? 's' : ''}`}
          {staleness.new_chunk_count > 0 && staleness.removed_chunk_count > 0 && ', '}
          {staleness.removed_chunk_count > 0 && `${staleness.removed_chunk_count} removed`}
          {' '}since this analysis ran. Re-analyze the affected clauses only.
        </p>
      </div>
      <button
        onClick={onReanalyze}
        disabled={reanalyzing}
        className="flex-shrink-0 flex items-center gap-1.5 rounded-lg border border-amber-400 bg-white px-3 py-1.5 text-xs font-semibold text-amber-900 hover:bg-amber-100 dark:border-amber-600 dark:bg-slate-900 dark:text-amber-200 dark:hover:bg-amber-950 disabled:opacity-60 transition-colors"
      >
        {reanalyzing && <Spinner size="sm" />}
        {reanalyzing ? 'Starting…' : 'Re-analyze differences'}
      </button>
    </div>
  )
}

