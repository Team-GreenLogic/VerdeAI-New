import { useEffect, useState } from 'react'
import {
  getProfile, updateProfile,
  getCompleteness, listClauses, getClause, updateClause,
} from '../api/orgProfile.js'
import Spinner from '../components/Spinner.jsx'

function ProgressBar({ pct }) {
  const color = pct >= 80 ? 'bg-brand-500' : pct >= 40 ? 'bg-amber-400' : 'bg-red-400'
  return (
    <div className="h-2 w-full rounded-full bg-slate-100">
      <div className={`h-2 rounded-full ${color} transition-all`} style={{ width: `${pct}%` }} />
    </div>
  )
}

function FieldInput({ field, value, onChange }) {
  const base = 'w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 transition-colors'
  if (field.field_type === 'boolean') {
    return (
      <button
        type="button"
        onClick={() => onChange(!value)}
        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${value ? 'bg-brand-600' : 'bg-slate-200'}`}
      >
        <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${value ? 'translate-x-6' : 'translate-x-1'}`} />
      </button>
    )
  }
  if (field.field_type === 'textarea') {
    return <textarea rows={3} value={value || ''} onChange={e => onChange(e.target.value)} className={base} />
  }
  return <input type="text" value={value || ''} onChange={e => onChange(e.target.value)} className={base} />
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

  // Pair short fields into rows
  const shortFields = FIELDS.slice(0, 4)
  const longFields = FIELDS.slice(4)

  return (
    <form onSubmit={handleSave} className="max-w-2xl space-y-4">
      {/* 2-column grid for short fields */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {shortFields.map(({ key, label }) => (
          <div key={key}>
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">{label}</label>
            <input
              type="text"
              value={form[key] || ''}
              onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
              className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 transition-colors"
            />
          </div>
        ))}
      </div>
      {/* Full-width fields */}
      {longFields.map(({ key, label }) => (
        <div key={key}>
          <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">{label}</label>
          <input
            type="text"
            value={form[key] || ''}
            onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
            className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20 transition-colors"
          />
        </div>
      ))}
      <button
        type="submit"
        disabled={saving}
        className={`flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-60 transition-colors ${saved ? 'bg-emerald-600' : 'bg-brand-600 hover:bg-brand-700'}`}
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
    <div className="flex flex-col md:flex-row gap-5 h-auto md:h-[600px]">
      {/* Clause list */}
      <div className="w-full md:w-56 flex-shrink-0 overflow-y-auto border border-slate-200 rounded-xl bg-white scrollbar-thin">
        {clauses.map(c => (
          <button
            key={c.clause_id}
            onClick={() => selectClause(c.clause_id)}
            className={`w-full text-left px-3 py-2.5 border-b border-slate-100 hover:bg-slate-50 transition-colors last:border-0 ${
              selected === c.clause_id ? 'bg-brand-50 border-l-2 border-l-brand-600' : ''
            }`}
          >
            <div className={`text-xs font-bold ${selected === c.clause_id ? 'text-brand-700' : 'text-slate-700'}`}>{c.clause_id}</div>
            <div className="text-xs text-slate-500 truncate">{c.title}</div>
            <div className="mt-1"><ProgressBar pct={c.pct} /></div>
            <div className="text-xs text-slate-400 mt-0.5 text-right">{c.filled}/{c.total}</div>
          </button>
        ))}
      </div>

      {/* Field editor */}
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {!selected && (
          <div className="flex h-full items-center justify-center text-slate-400 text-sm flex-col gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" className="w-8 h-8 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
            </svg>
            Select a clause to edit its fields
          </div>
        )}
        {selected && !clauseData && (
          <div className="flex h-full items-center justify-center"><Spinner size="lg" /></div>
        )}
        {clauseData && (
          <div className="space-y-4 pr-2">
            {/* Clause header */}
            <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-3 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-slate-800">{clauseData.clause_id}: {clauseData.title}</h3>
                <p className="text-xs text-slate-400 mt-0.5">{clauseData.fields.length} fields</p>
              </div>
              <span className="text-xs font-medium text-brand-600 bg-brand-50 rounded-full px-2.5 py-0.5">
                {values ? Object.values(values).filter(v => v !== null && v !== '' && v !== undefined).length : 0}/{clauseData.fields.length} filled
              </span>
            </div>

            {clauseData.fields.map(field => (
              <div key={field.field_path}>
                <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">
                  {field.label}
                  <span className="ml-2 font-mono font-normal text-slate-400 normal-case">{field.field_path}</span>
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
              className={`flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-60 transition-colors ${saved ? 'bg-emerald-600' : 'bg-brand-600 hover:bg-brand-700'}`}
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

  const pct = completeness?.overall_pct ?? 0

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      {/* Completeness banner — temporarily hidden */}
      {false && completeness && (
        <div className="rounded-xl bg-gradient-to-r from-brand-600 to-brand-700 text-white p-5">
          <div className="flex flex-col md:flex-row md:items-center gap-4">
            <div className="md:w-32 flex-shrink-0">
              <p className="text-brand-100 text-xs font-semibold uppercase tracking-wide">Completeness</p>
              <p className="text-4xl font-bold">{pct}%</p>
            </div>
            <div className="flex-1">
              <div className="h-4 rounded-full bg-brand-500/50 overflow-hidden">
                <div
                  className="h-4 rounded-full bg-white/60 transition-all"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <p className="text-brand-100 text-xs mt-1.5">
                {completeness.clauses_filled ?? 0} of 32 clauses documented
              </p>
            </div>
            <div className="flex-shrink-0 text-right">
              <button
                onClick={() => setTab('clauses')}
                className="text-xs font-semibold text-white underline underline-offset-2 hover:text-brand-100 transition-colors"
              >
                Complete Profile →
              </button>
            </div>
          </div>
        </div>
      )}

      <div>
        <h1 className="text-2xl font-bold text-slate-900">Organisation Profile</h1>
        <p className="text-sm text-slate-500 mt-1">Your profile data is used to personalise gap analysis and recommendations.</p>
      </div>

      {/* Pill tabs */}
      <div className="flex gap-1 bg-slate-100 p-1 rounded-xl w-fit">
        {/* Clause Fields tab — temporarily hidden */}
        {[['info', 'Organisation Info']].map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition-all ${
              tab === key
                ? 'bg-white shadow-sm text-slate-900'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="rounded-xl bg-white border border-slate-200 shadow-sm p-6">
        {tab === 'info' ? <OrgInfoTab /> : <ClauseFieldsTab />}
      </div>
    </div>
  )
}
