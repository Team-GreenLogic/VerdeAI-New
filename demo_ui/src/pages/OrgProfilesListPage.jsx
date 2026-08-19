import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createProfile } from '../api/orgProfiles.js'
import ProfilePicker from '../components/ProfilePicker.jsx'
import Spinner from '../components/Spinner.jsx'

function CreateModal({ onClose, onCreate }) {
  const [form, setForm] = useState({ org_name: '', org_industry: '', org_size: '', org_location: '', description: '' })
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setSaving(true)
    try {
      await onCreate(form)
      onClose()
    } catch (err) {
      alert(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="w-full max-w-md rounded-xl bg-white shadow-2xl p-6" onClick={e => e.stopPropagation()}>
        <h2 className="text-lg font-bold text-slate-900 mb-4">New Org Profile</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Organisation Name</label>
            <input
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
              value={form.org_name}
              onChange={e => setForm(f => ({ ...f, org_name: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">Industry</label>
              <input
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
                value={form.org_industry}
                onChange={e => setForm(f => ({ ...f, org_industry: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-600 mb-1">Size</label>
              <input
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
                value={form.org_size}
                onChange={e => setForm(f => ({ ...f, org_size: e.target.value }))}
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Location</label>
            <input
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
              value={form.org_location}
              onChange={e => setForm(f => ({ ...f, org_location: e.target.value }))}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Description</label>
            <textarea
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 resize-none"
              rows={3}
              placeholder="What this organisation does, and any context relevant to compliance"
              value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 transition-colors">
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50 transition-colors"
            >
              {saving && <Spinner size="sm" />}
              Create
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function OrgProfilesListPage() {
  const [showCreate, setShowCreate] = useState(false)
  const navigate = useNavigate()

  async function handleCreate(form) {
    const created = await createProfile(form)
    navigate(`/org-profiles/${created.profile_id}`)
  }

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      {showCreate && (
        <CreateModal onClose={() => setShowCreate(false)} onCreate={handleCreate} />
      )}

      <div className="rounded-xl bg-white border border-slate-200 border-l-4 border-l-brand-500 shadow-sm p-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-slate-900">Org Profiles</h1>
            <p className="text-sm text-slate-500 mt-0.5">Manage the organisation profiles used to personalise gap analysis and recommendations.</p>
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 transition-colors flex-shrink-0"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
            New Profile
          </button>
        </div>
      </div>

      <ProfilePicker
        onSelect={pid => navigate(`/org-profiles/${pid}`)}
        emptyHint="Create a profile to describe an organisation for compliance analysis."
      />
    </div>
  )
}

