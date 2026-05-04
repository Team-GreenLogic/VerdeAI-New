const STYLES = {
  // Analysis statuses
  pending:                'bg-gray-100 text-gray-700',
  running:                'bg-blue-100 text-blue-700 animate-pulse',
  paused:                 'bg-yellow-100 text-yellow-700',
  complete:               'bg-green-100 text-green-700',
  failed:                 'bg-red-100 text-red-700',
  deduped:                'bg-purple-100 text-purple-700',
  // Document statuses
  queued:                 'bg-gray-100 text-gray-700',
  processing:             'bg-blue-100 text-blue-700 animate-pulse',
  completed:              'bg-green-100 text-green-700',
  deleted:                'bg-gray-100 text-gray-400',
  // Gap decisions
  'Met':                  'bg-green-100 text-green-700',
  'Partially Met':        'bg-yellow-100 text-yellow-700',
  'Not Met':              'bg-red-100 text-red-700',
  'Insufficient Evidence':'bg-gray-100 text-gray-600',
  'Error':                'bg-red-100 text-red-700',
}

export default function Badge({ status, className = '' }) {
  const style = STYLES[status] || 'bg-gray-100 text-gray-600'
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${style} ${className}`}>
      {status}
    </span>
  )
}
