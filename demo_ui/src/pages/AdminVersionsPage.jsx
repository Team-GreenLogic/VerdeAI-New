import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listVersions, createVersion, deleteVersion, publishVersion, archiveVersion } from '../api/admin.js'
import Spinner from '../components/Spinner.jsx'

const STATUS_STYLES = {
  draft: 'bg-amber-100 text-amber-800',
  published: 'bg-green-100 text-green-800',
  archived: 'bg-slate-100 text-slate-500',
}

function StatusBadge({ status }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ${STATUS_STYLES[status] ?? 'bg-slate-100 text-slate-600'}`}>
      {status}
    </span>
  )
}

function CreateModal({ onClose, onCreate }) {
  const [form, setForm] = useState({ version_id: '', name: '', description: '' })
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!form.version_id.trim() || !form.name.trim()) return
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
        <h2 className="text-lg font-bold text-slate-900 mb-4">Create ISO Version</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Version ID <span className="text-red-500">*</span></label>
            <input
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
              placeholder="iso-14001-2024"
              value={form.version_id}
              onChange={e => setForm(f => ({ ...f, version_id: e.target.value.toLowerCase().replace(/\s+/g, '-') }))}
              required
            />
            <p className="text-xs text-slate-400 mt-1">Lowercase slug, e.g. iso-14001-2024</p>
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Name <span className="text-red-500">*</span></label>
            <input
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
              placeholder="ISO 14001:2024"
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              required
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Description</label>
            <textarea
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 resize-none"
              rows={2}
              placeholder="Optional description"
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
              className="flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-600 disabled:opacity-50 transition-colors"
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

export default function AdminVersionsPage() {
  const [versions, setVersions] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [actionId, setActionId] = useState(null)
  const navigate = useNavigate()

  async function refresh() {
    const data = await listVersions().catch(() => [])
    setVersions(data || [])
  }

  useEffect(() => {
    refresh().finally(() => setLoading(false))
  }, [])

  async function handleCreate(form) {
    await createVersion(form)
    await refresh()
  }

  async function handleAction(vid, action) {
    setActionId(vid + action)
    try {
      if (action === 'publish') await publishVersion(vid)
      else if (action === 'archive') await archiveVersion(vid)
      else if (action === 'delete') {
        if (!confirm(`Delete version "${vid}"? This cannot be undone.`)) return
        await deleteVersion(vid)
      }
      await refresh()
    } catch (err) {
      alert(err.message)
    } finally {
      setActionId(null)
    }
  }

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      {showCreate && (
        <CreateModal onClose={() => setShowCreate(false)} onCreate={handleCreate} />
      )}

      {/* Header */}
      <div className="rounded-xl bg-white border border-slate-200 border-l-4 border-l-amber-400 shadow-sm p-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-amber-600 bg-amber-50 rounded px-2 py-0.5">Admin</span>
              <h1 className="text-xl font-bold text-slate-900">ISO Versions</h1>
            </div>
            <p className="text-sm text-slate-500 mt-0.5">Manage the global catalog of ISO standard versions used for compliance analysis.</p>
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-semibold text-white hover:bg-amber-600 transition-colors flex-shrink-0"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
            New Version
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-10"><Spinner size="lg" /></div>
      ) : versions.length === 0 ? (
        <div className="rounded-xl bg-white border border-slate-200 p-12 text-center">
          <p className="text-sm font-semibold text-slate-600">No versions yet</p>
          <p className="text-xs text-slate-400 mt-1">Create a new version to get started.</p>
        </div>
      ) : (
        <div className="rounded-xl bg-white border border-slate-200 shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Version ID</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Name</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Status</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Source</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Clauses</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Created</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {versions.map(v => (
                <tr key={v.version_id} className="hover:bg-amber-50/30 transition-colors">
                  <td className="px-4 py-3">
                    <span className="font-mono text-xs bg-slate-100 text-slate-700 rounded px-1.5 py-0.5">{v.version_id}</span>
                  </td>
                  <td className="px-4 py-3 font-medium text-slate-800">{v.name}</td>
                  <td className="px-4 py-3"><StatusBadge status={v.status} /></td>
                  <td className="px-4 py-3 text-slate-500 capitalize">{v.source}</td>
                  <td className="px-4 py-3 text-slate-700">{v.clause_count ?? 0}</td>
                  <td className="px-4 py-3 text-xs text-slate-400">{new Date(v.created_at).toLocaleDateString()}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1.5">
                      <button
                        onClick={() => navigate(`/admin/versions/${v.version_id}`)}
                        className="text-xs font-semibold text-amber-600 hover:text-amber-700 bg-amber-50 hover:bg-amber-100 rounded-md px-2.5 py-1 transition-colors"
                      >
                        Manage
                      </button>
                      {v.status === 'draft' && (
                        <button
                          onClick={() => handleAction(v.version_id, 'publish')}
                          disabled={actionId === v.version_id + 'publish'}
                          className="text-xs font-semibold text-green-700 bg-green-50 hover:bg-green-100 rounded-md px-2.5 py-1 transition-colors disabled:opacity-50"
                        >
                          Publish
                        </button>
                      )}
                      {v.status === 'published' && (
                        <button
                          onClick={() => handleAction(v.version_id, 'archive')}
                          disabled={actionId === v.version_id + 'archive'}
                          className="text-xs font-semibold text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-md px-2.5 py-1 transition-colors disabled:opacity-50"
                        >
                          Archive
                        </button>
                      )}
                      {v.status === 'draft' && v.source !== 'seed' && (
                        <button
                          onClick={() => handleAction(v.version_id, 'delete')}
                          disabled={actionId === v.version_id + 'delete'}
                          className="text-xs font-semibold text-red-600 bg-red-50 hover:bg-red-100 rounded-md px-2.5 py-1 transition-colors disabled:opacity-50"
                        >
                          Delete
                        </button>
                      )}
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
