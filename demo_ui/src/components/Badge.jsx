const STYLES = {
  // Analysis statuses
  pending:                 'border border-slate-200 bg-slate-100 text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200',
  running:                 'border border-blue-200 bg-blue-100 text-blue-800 dark:border-blue-700 dark:bg-blue-950/60 dark:text-blue-200 animate-pulse',
  paused:                  'border border-amber-200 bg-amber-100 text-amber-800 dark:border-amber-700 dark:bg-amber-950/60 dark:text-amber-200',
  complete:                'border border-emerald-200 bg-emerald-100 text-emerald-800 dark:border-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-200',
  failed:                  'border border-red-200 bg-red-100 text-red-800 dark:border-red-700 dark:bg-red-950/60 dark:text-red-200',
  deduped:                 'border border-purple-200 bg-purple-100 text-purple-800 dark:border-purple-700 dark:bg-purple-950/60 dark:text-purple-200',
  // Document statuses
  queued:                  'border border-slate-200 bg-slate-100 text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200',
  processing:              'border border-blue-200 bg-blue-100 text-blue-800 dark:border-blue-700 dark:bg-blue-950/60 dark:text-blue-200 animate-pulse',
  completed:               'border border-emerald-200 bg-emerald-100 text-emerald-800 dark:border-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-200',
  ready:                   'border border-emerald-200 bg-emerald-100 text-emerald-800 dark:border-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-200',
  deleted:                 'border border-slate-200 bg-slate-100 text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400',
  superseded:              'border border-slate-200 bg-slate-100 text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400',
  // Gap decisions
  'Met':                   'border border-emerald-200 bg-emerald-100 text-emerald-800 dark:border-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-200',
  'Partially Met':         'border border-amber-200 bg-amber-100 text-amber-900 dark:border-amber-700 dark:bg-amber-950/60 dark:text-amber-200',
  'Not Met':               'border border-red-200 bg-red-100 text-red-800 dark:border-red-700 dark:bg-red-950/60 dark:text-red-200',
  'Insufficient Evidence': 'border border-slate-200 bg-slate-100 text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200',
  'Error':                 'border border-red-200 bg-red-100 text-red-800 dark:border-red-700 dark:bg-red-950/60 dark:text-red-200',
}

const DECISION_ICONS = {
  'Met': '✓',
  'Partially Met': '!',
  'Not Met': '×',
  'Insufficient Evidence': 'i',
  'Error': '×',
}

const DOT_COLORS = {
  running:                 'bg-blue-500 animate-pulse',
  processing:              'bg-blue-500 animate-pulse',
  complete:                'bg-emerald-500',
  completed:               'bg-emerald-500',
  failed:                  'bg-red-500',
  'Error':                 'bg-red-500',
  paused:                  'bg-amber-500',
  pending:                 'bg-slate-400',
  queued:                  'bg-slate-400',
  ready:                   'bg-emerald-500',
  deduped:                 'bg-purple-500',
  superseded:              'bg-slate-400',
  'Met':                   'bg-emerald-500',
  'Partially Met':         'bg-amber-500',
  'Not Met':               'bg-red-500',
  'Insufficient Evidence': 'bg-slate-400',
}

export default function Badge({ status, className = '' }) {
  const style = STYLES[status] || 'border border-slate-200 bg-slate-100 text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200'
  const dot = DOT_COLORS[status]
  const decisionIcon = DECISION_ICONS[status]
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${style} ${className}`}>
      {decisionIcon
        ? <span aria-hidden="true" className="flex h-3.5 w-3.5 items-center justify-center rounded-full border border-current text-[9px] font-bold leading-none">{decisionIcon}</span>
        : dot && <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dot}`} />}
      {status}
    </span>
  )
}

