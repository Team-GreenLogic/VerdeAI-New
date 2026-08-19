import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listProfiles } from '../api/orgProfiles.js'
import Spinner from './Spinner.jsx'

const BuildingSVG = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-12 h-12" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
  </svg>
)

export default function ProfilePicker({ onSelect, emptyHint, showCreateButton = false }) {
  const [profiles, setProfiles] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listProfiles().then(p => setProfiles(p || [])).catch(() => setProfiles([])).finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="flex justify-center py-10"><Spinner size="lg" /></div>

  if (profiles.length === 0) {
    return (
      <div className="rounded-xl bg-white border border-slate-200 p-12 text-center">
        <div className="flex justify-center text-slate-300 mb-3">
          <BuildingSVG />
        </div>
        <p className="text-sm font-semibold text-slate-600">No org profiles yet</p>
        {emptyHint && <p className="text-xs text-slate-400 mt-1">{emptyHint}</p>}
        {showCreateButton && (
          <Link
            to="/org-profiles"
            className="inline-flex items-center gap-2 mt-4 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 transition-colors"
          >
            Create your first org profile
          </Link>
        )}
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
      {profiles.map(p => {
        const subtitle = [p.org_industry, p.org_location].filter(Boolean).join(' · ')
        return (
          <button
            key={p.profile_id}
            onClick={() => onSelect(p.profile_id)}
            className="text-left rounded-xl border-2 border-slate-200 bg-white p-4 hover:border-brand-400 hover:bg-brand-50/40 hover:shadow-md transition-all"
          >
            <div className="flex items-start gap-3">
              <span className="flex items-center justify-center w-10 h-10 rounded-full bg-brand-50 text-brand-600 flex-shrink-0">
                <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                </svg>
              </span>
              <div className="min-w-0">
                <p className="text-sm font-bold text-slate-800 truncate">{p.org_name || 'Untitled Profile'}</p>
                {subtitle && <p className="text-xs text-slate-500 mt-0.5 truncate">{subtitle}</p>}
              </div>
            </div>
          </button>
        )
      })}
    </div>
  )
}

