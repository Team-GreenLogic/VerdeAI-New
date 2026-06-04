const STYLES = {
  // Analysis statuses
  pending:                 'bg-slate-100 text-slate-600',
  running:                 'bg-blue-100 text-blue-700 animate-pulse',
  paused:                  'bg-amber-100 text-amber-700',
  complete:                'bg-emerald-100 text-emerald-700',
  failed:                  'bg-red-100 text-red-700',
  deduped:                 'bg-purple-100 text-purple-700',
  // Document statuses
  queued:                  'bg-slate-100 text-slate-600',
  processing:              'bg-blue-100 text-blue-700 animate-pulse',
  completed:               'bg-emerald-100 text-emerald-700',
  deleted:                 'bg-slate-100 text-slate-400',
  // Gap decisions
  'Met':                   'bg-emerald-100 text-emerald-700',
  'Partially Met':         'bg-amber-100 text-amber-700',
  'Not Met':               'bg-red-100 text-red-700',
  'Insufficient Evidence': 'bg-slate-100 text-slate-600',
  'Error':                 'bg-red-100 text-red-700',
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
  deduped:                 'bg-purple-500',
  'Met':                   'bg-emerald-500',
  'Partially Met':         'bg-amber-500',
  'Not Met':               'bg-red-500',
  'Insufficient Evidence': 'bg-slate-400',
}

export default function Badge({ status, className = '' }) {
  const style = STYLES[status] || 'bg-slate-100 text-slate-600'
  const dot = DOT_COLORS[status]
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${style} ${className}`}>
      {dot && <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dot}`} />}
      {status}
    </span>
  )
}
