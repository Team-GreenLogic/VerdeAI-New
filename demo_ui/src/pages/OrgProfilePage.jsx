import { useEffect, useState } from 'react'
import {
  getProfile, updateProfile,
  getCompleteness, listClauses, getClause, updateClause,
} from '../api/orgProfile.js'
import Spinner from '../components/Spinner.jsx'

function ProgressBar({ pct }) {
  const color = pct >= 80 ? 'bg-brand-500' : pct >= 40 ? 'bg-yellow-400' : 'bg-red-400'
  return (
    <div className="h-1.5 w-full rounded-full bg-gray-100">
      <div className={`h-1.5 rounded-full ${color} transition-all`} style={{ width: `${pct}%` }} />
    </div>
  )
}

function FieldInput({ field, value, onChange }) {
  const base = 'w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500'
  if (field.field_type === 'boolean') {
    return (
      <button
        type="button"
        onClick={() => onChange(!value)}
        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${value ? 'bg-brand-600' : 'bg-gray-200'}`}
      >
        <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${value ? 'translate-x-6' : 'translate-x-1'}`} />
      </button>
    )
  }
  if (field.field_type === 'textarea') {
    return (
      <textarea
        rows={3}
        value={value || ''}
        onChange={e => onChange(e.target.value)}
        className={base}
      />
    )
  }
  return (
    <input
      type="text"
      value={value || ''}
      onChange={e => onChange(e.target.value)}
      className={base}
    />
  )
}

// Tab 1: Org Info
function OrgInfoTab() {
  const FIELDS = [
    { key: 'org_name', label: 'Organisation Name' },
    { key: 'org_industry', label: 'Industry' },
    { key: 'org_size', label: 'Organisation Size' },
    { key: 'org_location', label: 'Location' },
    { key: 'primary_activities', label: 'Primary Activities' },
    { key: 'leadership_roles', label: 'Key Leadership Roles' },
  ]
  const [form, setForm] = useState({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    getProfile().then(p => { setForm(p || {}); setLoading(false) })
  }, [])

  async function handleSave(e) {
    e.preventDefault()
    setSaving(true)
    try {
      await updateProfile(form)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err) {
      alert(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="flex justify-center py-10"><Spinner size="lg" /></div>

  return (
    <form onSubmit={handleSave} className="max-w-lg space-y-4">
      {FIELDS.map(({ key, label }) => (
        <div key={key}>
          <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
          <input
            type="text"
            value={form[key] || ''}
            onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
            className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>
      ))}
      <button
        type="submit"
        disabled={saving}
        className="flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60 transition-colors"
      >
        {saving && <Spinner size="sm" />}
        {saved ? '✓ Saved' : 'Save Changes'}
      </button>
    </form>
  )
}

// Tab 2: Clause Fields
function ClauseFieldsTab() {
  const [clauses, setClauses] = useState([])
  const [selected, setSelected] = useState(null)
  const [clauseData, setClauseData] = useState(null)
  const [values, setValues] = useState({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listClauses().then(c => { setClauses(c || []); setLoading(false) })
  }, [])

  async function selectClause(clauseId) {
    setSelected(clauseId)
    setClauseData(null)
    setSaved(false)
    const data = await getClause(clauseId)
    setClauseData(data)
    const vals = {}
    data.fields.forEach(f => { vals[f.field_path] = f.value })
    setValues(vals)
  }

  async function handleSave() {
    setSaving(true)
    try {
      await updateClause(selected, values)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      // Refresh completeness
      const updated = await listClauses()
      setClauses(updated || [])
    } catch (err) {
      alert(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="flex justify-center py-10"><Spinner size="lg" /></div>

  return (
    <div className="flex gap-5 h-[600px]">
      {/* Clause list */}
      <div className="w-52 flex-shrink-0 overflow-y-auto border border-gray-100 rounded-xl bg-white">
        {clauses.map(c => (
          <button
            key={c.clause_id}
            onClick={() => selectClause(c.clause_id)}
            className={`w-full text-left px-3 py-2.5 border-b border-gray-50 hover:bg-gray-50 transition-colors ${selected === c.clause_id ? 'bg-brand-50 border-l-2 border-l-brand-600' : ''}`}
          >
            <div className="text-xs font-semibold text-gray-700">{c.clause_id}</div>
            <div className="text-xs text-gray-500 truncate">{c.title}</div>
            <ProgressBar pct={c.pct} />
            <div className="text-xs text-gray-400 mt-0.5">{c.filled}/{c.total}</div>
          </button>
        ))}
      </div>

      {/* Field editor */}
      <div className="flex-1 overflow-y-auto">
        {!selected && (
          <div className="flex h-full items-center justify-center text-gray-400 text-sm">
            Select a clause to edit its fields
          </div>
        )}
        {selected && !clauseData && (
          <div className="flex h-full items-center justify-center"><Spinner size="lg" /></div>
        )}
        {clauseData && (
          <div className="space-y-4 pr-2">
            <div>
              <h3 className="font-semibold text-gray-800">{clauseData.clause_id}: {clauseData.title}</h3>
              <p className="text-xs text-gray-400 mt-0.5">{clauseData.fields.length} fields</p>
            </div>
            {clauseData.fields.map(field => (
              <div key={field.field_path}>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {field.label}
                  <span className="ml-2 text-xs text-gray-400 font-normal">{field.field_path}</span>
                </label>
                <FieldInput
                  field={field}
                  value={values[field.field_path]}
                  onChange={v => setValues(vals => ({ ...vals, [field.field_path]: v }))}
                />
              </div>
            ))}
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60 transition-colors"
            >
              {saving && <Spinner size="sm" />}
              {saved ? '✓ Saved' : 'Save Clause'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default function OrgProfilePage() {
  const [tab, setTab] = useState('info')
  const [completeness, setCompleteness] = useState(null)

  useEffect(() => {
    getCompleteness().then(c => setCompleteness(c)).catch(() => {})
  }, [])

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Organisation Profile</h1>
        <p className="text-sm text-gray-500 mt-1">Your profile data is used to personalise gap analysis and recommendations.</p>
      </div>

      {/* Completeness banner */}
      {completeness && (
        <div className="rounded-xl bg-white border border-gray-100 shadow-sm p-4 flex items-center gap-4">
          <div className="flex-1">
            <div className="flex justify-between text-sm mb-1">
              <span className="font-medium text-gray-700">Overall Completeness</span>
              <span className="font-bold text-brand-600">{completeness.overall_pct}%</span>
            </div>
            <div className="h-2 rounded-full bg-gray-100">
              <div
                className="h-2 rounded-full bg-brand-500 transition-all"
                style={{ width: `${completeness.overall_pct}%` }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200">
        {[['info', '🏢 Organisation Info'], ['clauses', '📋 Clause Fields']].map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === key
                ? 'border-brand-600 text-brand-700'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="rounded-xl bg-white border border-gray-100 shadow-sm p-6">
        {tab === 'info' ? <OrgInfoTab /> : <ClauseFieldsTab />}
      </div>
    </div>
  )
}
