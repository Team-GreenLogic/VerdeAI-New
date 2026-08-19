import { useEffect, useState, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  getVersion, listClauses, getClause, createClause, updateClause, deleteClause,
  getClauseTemplate, updateClauseTemplate, uploadSourceDoc, deleteSourceDoc, triggerBuild,
  pauseBuild, resumeBuild, resetBuild, publishVersion, archiveVersion
} from '../api/admin.js'
import { useJobProgress } from '../hooks/useJobProgress.js'
import Spinner from '../components/Spinner.jsx'
import { SlotSchemaList, SlotSummary } from '../components/Slots.jsx'

// ─── Shared helpers ─────────────────────────────────────────────────────────

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

// ─── Clauses Tab ─────────────────────────────────────────────────────────────

/**
 * The slot schema for one clause: what information ISO requires, and which pieces are
 * mandatory. `required` is what the gap analyser derives its verdict from, so this is
 * worth reading before trusting a run — see docs/gap-analysis.md §2.1.
 */
function ClauseSlots({ clause }) {
  const [open, setOpen] = useState(false)
  const slots = clause.slot_schema || []

  // A title-only ISO heading (6.1, 6.2, 7.4, 7.5, 9.1, 9.2 — verified against ISO 14001:2015;
  // the normative "shall" text starts only at the .1 sub-clause) has no requirements of its
  // own, so it deliberately has no schema — distinct from a leaf clause whose schema simply
  // hasn't been generated yet. Conflating the two used to read as "this needs make gen-slots".
  if (clause.title_only) {
    return (
      <p className="mt-2 text-[11px] text-slate-400">
        Section — derived from sub-clauses, not independently analysed.
      </p>
    )
  }

  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-500 hover:text-amber-600 transition-colors"
      >
        <svg
          className={`w-3 h-3 transition-transform ${open ? 'rotate-90' : ''}`}
          fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
        Requirement slots
        {slots.length > 0
          ? <SlotSummary slots={slots} />
          : <span className="text-[11px] text-slate-400 font-normal">not generated</span>}
      </button>
      {open && (
        <div className="mt-2">
          <SlotSchemaList slots={slots} />
        </div>
      )}
    </div>
  )
}

function ClauseEditor({ vid, clause, onSaved, onCancel }) {
  const [form, setForm] = useState({
    clause_id: clause?.clause_id ?? '',
    section: clause?.section ?? '',
    title: clause?.title ?? '',
    requirements: clause?.requirements ?? '',
    search_query: clause?.search_query ?? '',
    keywords: clause?.keywords?.join(', ') ?? '',
  })
  const [saving, setSaving] = useState(false)
  const isNew = !clause

  async function handleSubmit(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const body = {
        ...form,
        keywords: form.keywords.split(',').map(k => k.trim()).filter(Boolean),
      }
      if (isNew) await createClause(vid, body)
      else await updateClause(vid, clause.clause_id, body)
      onSaved()
    } catch (err) {
      alert(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="bg-amber-50 border border-amber-200 rounded-xl p-5 space-y-3">
      <h3 className="text-sm font-bold text-slate-800">{isNew ? 'Add Clause' : `Edit ${clause.clause_id}`}</h3>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-semibold text-slate-600 mb-1">Clause ID {isNew && <span className="text-red-500">*</span>}</label>
          <input
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
            placeholder="4.1"
            value={form.clause_id}
            onChange={e => setForm(f => ({ ...f, clause_id: e.target.value }))}
            required
            disabled={!isNew}
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-600 mb-1">Section</label>
          <input
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
            placeholder="4.1"
            value={form.section}
            onChange={e => setForm(f => ({ ...f, section: e.target.value }))}
          />
        </div>
      </div>
      <div>
        <label className="block text-xs font-semibold text-slate-600 mb-1">Title <span className="text-red-500">*</span></label>
        <input
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
          placeholder="Understanding the organisation and its context"
          value={form.title}
          onChange={e => setForm(f => ({ ...f, title: e.target.value }))}
          required
        />
      </div>
      <div>
        <label className="block text-xs font-semibold text-slate-600 mb-1">Requirements</label>
        <textarea
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 resize-none"
          rows={4}
          placeholder="Normative requirements text..."
          value={form.requirements}
          onChange={e => setForm(f => ({ ...f, requirements: e.target.value }))}
        />
      </div>
      <div>
        <label className="block text-xs font-semibold text-slate-600 mb-1">Search Query</label>
        <p className="text-[11px] text-slate-400 mb-1">Used to search the tenant's uploaded documents for evidence — phrase it like a search, not the clause text.</p>
        <textarea
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 resize-none"
          rows={2}
          placeholder="environmental policy document, legal register, compliance procedure..."
          value={form.search_query}
          onChange={e => setForm(f => ({ ...f, search_query: e.target.value }))}
        />
      </div>
      <div>
        <label className="block text-xs font-semibold text-slate-600 mb-1">Keywords (comma-separated)</label>
        <input
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
          placeholder="context, internal, external"
          value={form.keywords}
          onChange={e => setForm(f => ({ ...f, keywords: e.target.value }))}
        />
      </div>
      <div className="flex justify-end gap-3">
        <button type="button" onClick={onCancel} className="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 transition-colors">
          Cancel
        </button>
        <button
          type="submit"
          disabled={saving}
          className="flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-600 disabled:opacity-50 transition-colors"
        >
          {saving && <Spinner size="sm" />}
          {isNew ? 'Add' : 'Save'}
        </button>
      </div>
    </form>
  )
}

function ClausesTab({ vid, version }) {
  const [clauses, setClauses] = useState([])
  const [loading, setLoading] = useState(true)
  const [editingId, setEditingId] = useState(null)
  const [showAdd, setShowAdd] = useState(false)
  const [deletingId, setDeletingId] = useState(null)

  async function refresh() {
    const data = await listClauses(vid).catch(() => [])
    setClauses(data || [])
  }

  useEffect(() => {
    refresh().finally(() => setLoading(false))
  }, [vid])

  async function handleDelete(cid) {
    if (!confirm(`Delete clause ${cid}?`)) return
    setDeletingId(cid)
    try {
      await deleteClause(vid, cid)
      await refresh()
    } catch (err) {
      alert(err.message)
    } finally {
      setDeletingId(null)
    }
  }

  if (loading) return <div className="flex justify-center py-10"><Spinner size="lg" /></div>

  const isEditable = version.status === 'draft'

  return (
    <div className="space-y-4">
      {isEditable && !showAdd && !editingId && (
        <div className="flex justify-end">
          <button
            onClick={() => setShowAdd(true)}
            className="flex items-center gap-2 rounded-lg bg-amber-500 px-3 py-2 text-sm font-semibold text-white hover:bg-amber-600 transition-colors"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
            </svg>
            Add Clause
          </button>
        </div>
      )}

      {showAdd && (
        <ClauseEditor vid={vid} onSaved={() => { setShowAdd(false); refresh() }} onCancel={() => setShowAdd(false)} />
      )}

      {clauses.length === 0 && !showAdd ? (
        <div className="text-center py-10 text-slate-400 text-sm">No clauses yet.</div>
      ) : (
        <div className="space-y-2">
          {clauses.map(c => (
            <div key={c.clause_id}>
              {editingId === c.clause_id ? (
                <ClauseEditor
                  vid={vid}
                  clause={c}
                  onSaved={() => { setEditingId(null); refresh() }}
                  onCancel={() => setEditingId(null)}
                />
              ) : (
                <div className="rounded-xl bg-white border border-slate-200 p-4 hover:border-amber-300 transition-colors">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-mono text-xs bg-slate-100 text-slate-700 rounded px-1.5 py-0.5 flex-shrink-0">{c.clause_id}</span>
                        <span className="font-semibold text-slate-800 text-sm truncate">{c.title}</span>
                      </div>
                      {c.requirements && (
                        <p className="text-xs text-slate-500 line-clamp-2 mt-1">{c.requirements}</p>
                      )}
                      {c.search_query && (
                        <p className="text-[11px] text-amber-600 italic line-clamp-1 mt-1">🔍 {c.search_query}</p>
                      )}
                      {c.keywords?.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {c.keywords.slice(0, 5).map(k => (
                            <span key={k} className="text-[10px] bg-slate-100 text-slate-500 rounded px-1.5 py-0.5">{k}</span>
                          ))}
                        </div>
                      )}
                      <ClauseSlots clause={c} />
                    </div>
                    {isEditable && (
                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        <button
                          onClick={() => setEditingId(c.clause_id)}
                          className="text-xs font-semibold text-amber-600 bg-amber-50 hover:bg-amber-100 rounded-md px-2 py-1 transition-colors"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleDelete(c.clause_id)}
                          disabled={deletingId === c.clause_id}
                          className="text-xs font-semibold text-red-600 bg-red-50 hover:bg-red-100 rounded-md px-2 py-1 transition-colors disabled:opacity-50"
                        >
                          {deletingId === c.clause_id ? <Spinner size="sm" /> : 'Delete'}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Template Tab ─────────────────────────────────────────────────────────────

function TemplateTab({ vid, version }) {
  const [clauses, setClauses] = useState([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(null)
  const [templateData, setTemplateData] = useState({})
  const [editingClause, setEditingClause] = useState(null)
  const [saving, setSaving] = useState(false)

  async function refresh() {
    const data = await listClauses(vid).catch(() => [])
    setClauses(data || [])
  }

  useEffect(() => {
    refresh().finally(() => setLoading(false))
  }, [vid])

  async function handleExpand(cid) {
    if (expanded === cid) { setExpanded(null); return }
    setExpanded(cid)
    if (!templateData[cid]) {
      const data = await getClauseTemplate(vid, cid).catch(() => ({ fields: [] }))
      setTemplateData(prev => ({ ...prev, [cid]: data.fields ?? [] }))
    }
  }

  async function handleSaveTemplate(cid) {
    setSaving(true)
    try {
      await updateClauseTemplate(vid, cid, templateData[cid])
      setEditingClause(null)
    } catch (err) {
      alert(err.message)
    } finally {
      setSaving(false)
    }
  }

  function updateField(cid, idx, key, val) {
    setTemplateData(prev => {
      const fields = [...(prev[cid] ?? [])]
      fields[idx] = { ...fields[idx], [key]: val }
      return { ...prev, [cid]: fields }
    })
  }

  if (loading) return <div className="flex justify-center py-10"><Spinner size="lg" /></div>

  const isEditable = version.status === 'draft'

  return (
    <div className="space-y-2">
      {clauses.map(c => (
        <div key={c.clause_id} className="rounded-xl bg-white border border-slate-200 overflow-hidden">
          <button
            className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-slate-50 transition-colors"
            onClick={() => handleExpand(c.clause_id)}
          >
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs bg-slate-100 text-slate-700 rounded px-1.5 py-0.5">{c.clause_id}</span>
              <span className="text-sm font-semibold text-slate-800">{c.title}</span>
            </div>
            <svg
              className={`w-4 h-4 text-slate-400 transition-transform ${expanded === c.clause_id ? 'rotate-180' : ''}`}
              fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {expanded === c.clause_id && (
            <div className="border-t border-slate-100 p-4">
              {!templateData[c.clause_id] ? (
                <div className="flex justify-center py-4"><Spinner size="sm" /></div>
              ) : templateData[c.clause_id].length === 0 ? (
                <p className="text-xs text-slate-400 text-center py-2">No template fields.</p>
              ) : (
                <div className="space-y-3">
                  {templateData[c.clause_id].map((field, idx) => (
                    <div key={field.field_path} className="grid grid-cols-3 gap-3 items-start">
                      <div>
                        <label className="block text-[10px] font-semibold text-slate-500 mb-1">Field Path</label>
                        <p className="font-mono text-xs text-slate-700 bg-slate-50 rounded px-2 py-1.5">{field.field_path}</p>
                      </div>
                      <div>
                        <label className="block text-[10px] font-semibold text-slate-500 mb-1">Label</label>
                        {editingClause === c.clause_id ? (
                          <input
                            className="w-full rounded border border-slate-300 px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-amber-400"
                            value={field.label ?? ''}
                            onChange={e => updateField(c.clause_id, idx, 'label', e.target.value)}
                          />
                        ) : (
                          <p className="text-xs text-slate-600 bg-slate-50 rounded px-2 py-1.5">{field.label ?? '—'}</p>
                        )}
                      </div>
                      <div>
                        <label className="block text-[10px] font-semibold text-slate-500 mb-1">Type</label>
                        <p className="text-xs text-slate-600 bg-slate-50 rounded px-2 py-1.5">{field.field_type ?? '—'}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {isEditable && templateData[c.clause_id]?.length > 0 && (
                <div className="flex justify-end gap-2 mt-3 pt-3 border-t border-slate-100">
                  {editingClause === c.clause_id ? (
                    <>
                      <button onClick={() => setEditingClause(null)} className="text-xs text-slate-500 hover:text-slate-700 px-3 py-1.5 rounded transition-colors">
                        Cancel
                      </button>
                      <button
                        onClick={() => handleSaveTemplate(c.clause_id)}
                        disabled={saving}
                        className="flex items-center gap-1.5 text-xs font-semibold text-white bg-amber-500 hover:bg-amber-600 px-3 py-1.5 rounded transition-colors disabled:opacity-50"
                      >
                        {saving && <Spinner size="sm" />} Save
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => setEditingClause(c.clause_id)}
                      className="text-xs font-semibold text-amber-600 bg-amber-50 hover:bg-amber-100 rounded px-3 py-1.5 transition-colors"
                    >
                      Edit Labels
                    </button>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// ─── Build Tab ────────────────────────────────────────────────────────────────

const PIPELINE_STAGES = [
  { key: 'parse',     label: 'Parse Documents',     desc: 'LlamaParse converts PDF/DOCX to markdown' },
  { key: 'structure', label: 'Detect Structure',    desc: 'LLM extracts clause outline from text' },
  { key: 'extract',  label: 'Extract Clauses',      desc: 'Per-clause requirements extracted in parallel' },
  { key: 'verify',   label: 'Verify Coverage',      desc: 'Verifier agent checks nothing was dropped' },
  { key: 'template', label: 'Generate Template',    desc: 'State template fields built for each clause' },
  { key: 'persist',  label: 'Persist to Database',  desc: 'Embeddings generated and saved to MongoDB' },
  { key: 'complete', label: 'Complete',             desc: 'Version is ready to review' },
]

function StageIndicator({ stageKey, stageStatus }) {
  // stageStatus: 'pending' | 'active' | 'done' | 'failed'
  const colors = {
    pending: 'bg-slate-100 text-slate-400 border-slate-200',
    active:  'bg-amber-50 text-amber-700 border-amber-300',
    done:    'bg-green-50 text-green-700 border-green-300',
    failed:  'bg-red-50 text-red-700 border-red-300',
  }
  const icons = {
    pending: <div className="w-3 h-3 rounded-full border-2 border-slate-300" />,
    active:  <div className="w-3 h-3 rounded-full border-2 border-amber-500 border-t-transparent animate-spin" />,
    done:    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>,
    failed:  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>,
  }
  const stage = PIPELINE_STAGES.find(s => s.key === stageKey)
  return (
    <div className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium transition-colors ${colors[stageStatus]}`}>
      <span className="flex-shrink-0">{icons[stageStatus]}</span>
      <span>{stage?.label ?? stageKey}</span>
    </div>
  )
}

function usePipelineStages(messages, jobStatus) {
  // Derive stage statuses and extracted clause list from progress messages
  const stageOrder = ['parse', 'structure', 'extract', 'verify', 'template', 'persist', 'complete']
  const stageMap = { detect_structure: 'structure', extract_clauses: 'extract', verify_coverage: 'verify', gen_state_template: 'template' }

  const seen = new Set()
  const extractedClauses = []

  for (const msg of messages) {
    const raw = msg.stage ?? ''
    const key = stageMap[raw] || raw
    seen.add(key)
    if (key === 'extract' && msg.detail?.startsWith('Extracted clause ')) {
      const cid = msg.detail.replace('Extracted clause ', '').trim()
      if (cid) extractedClauses.push(cid)
    }
  }

  const isDone = jobStatus === 'done'
  const isFailed = jobStatus === 'failed'
  const isPaused = messages.some(m => m.status === 'paused')
  const lastSeen = [...seen].filter(k => stageOrder.includes(k))
  const currentStageIdx = lastSeen.length > 0 ? stageOrder.indexOf(lastSeen[lastSeen.length - 1]) : -1

  const stages = stageOrder.map((key, idx) => {
    if (isFailed && idx === currentStageIdx) return { key, status: 'failed' }
    if (isDone || seen.has('complete') || idx < currentStageIdx) return { key, status: 'done' }
    if (idx === currentStageIdx && !isDone) return { key, status: isPaused ? 'done' : 'active' }
    return { key, status: 'pending' }
  })

  return { stages, extractedClauses }
}

function BuildTab({ vid, version, onVersionUpdated }) {
  const [uploading, setUploading] = useState(false)
  const [building, setBuilding] = useState(false)
  const [pausing, setPausing] = useState(false)
  const [resuming, setResuming] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [removingDoc, setRemovingDoc] = useState(null)
  const [buildJobId, setBuildJobId] = useState(version.build_job_id ?? null)
  const [buildStatus, setBuildStatus] = useState(version.build_status ?? 'idle')
  const [dragOver, setDragOver] = useState(false)
  const { messages, status: jobStatus, isConnected } = useJobProgress(buildJobId)
  const { stages, extractedClauses } = usePipelineStages(messages, jobStatus)
  const fileInputRef = useRef(null)
  const logRef = useRef(null)

  // Sync buildStatus from live progress messages
  useEffect(() => {
    if (jobStatus === 'done') setBuildStatus('done')
    else if (jobStatus === 'failed') setBuildStatus('failed')
    else {
      const pausedMsg = messages.find(m => m.status === 'paused')
      if (pausedMsg) setBuildStatus('paused')
    }
  }, [jobStatus, messages])

  const sourceDocs = version.source_docs ?? []
  const isEditable = version.status === 'draft'
  const buildDone = jobStatus === 'done' || jobStatus === 'failed'
  const isPaused = buildStatus === 'paused' || version.build_status === 'paused'
  const buildRunning = buildJobId && !buildDone && !isPaused

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [messages])

  async function handleFiles(fileList) {
    for (const file of fileList) {
      if (!file.name.match(/\.(pdf|docx|doc)$/i)) {
        alert(`Unsupported file type: ${file.name}. Only PDF/DOCX allowed.`)
        continue
      }
      setUploading(true)
      try {
        const fd = new FormData()
        fd.append('file', file)
        await uploadSourceDoc(vid, fd)
        await onVersionUpdated()
      } catch (err) {
        alert(`Upload failed for ${file.name}: ${err.message}`)
      } finally {
        setUploading(false)
      }
    }
  }

  async function handleFileInput(e) {
    if (e.target.files?.length) await handleFiles(Array.from(e.target.files))
    e.target.value = ''
  }

  async function handleDrop(e) {
    e.preventDefault()
    setDragOver(false)
    await handleFiles(Array.from(e.dataTransfer.files))
  }

  async function handleRemoveDoc(gridfsId, filename) {
    if (!confirm(`Remove "${filename}"?`)) return
    setRemovingDoc(gridfsId)
    try {
      await deleteSourceDoc(vid, gridfsId)
      await onVersionUpdated()
    } catch (err) {
      alert(err.message)
    } finally {
      setRemovingDoc(null)
    }
  }

  async function handleBuild() {
    if (!confirm('Start AI build? This replaces any previously extracted clauses.')) return
    setBuilding(true)
    try {
      const res = await triggerBuild(vid)
      setBuildJobId(res.build_job_id)
      setBuildStatus('building')
      await onVersionUpdated()
    } catch (err) {
      alert(err.message)
    } finally {
      setBuilding(false)
    }
  }

  async function handleReset() {
    if (!confirm('Reset the stuck build? This clears the job ID so you can start fresh.')) return
    setResetting(true)
    try {
      await resetBuild(vid)
      setBuildJobId(null)
      setBuildStatus('idle')
      await onVersionUpdated()
    } catch (err) {
      alert(err.message)
    } finally {
      setResetting(false)
    }
  }

  async function handlePause() {
    setPausing(true)
    try {
      await pauseBuild(vid)
      setBuildStatus('pause_requested')
    } catch (err) {
      alert(err.message)
    } finally {
      setPausing(false)
    }
  }

  async function handleResume() {
    setResuming(true)
    try {
      const res = await resumeBuild(vid)
      setBuildJobId(res.build_job_id)
      setBuildStatus('building')
      await onVersionUpdated()
    } catch (err) {
      alert(err.message)
    } finally {
      setResuming(false)
    }
  }

  // Find clause count from done message
  const doneMsg = messages.find(m => m.status === 'done')
  const finalClauseCount = doneMsg?.clause_count ?? null

  // Live detail log (only show last 60 messages to avoid clutter)
  const logMessages = messages.slice(-60)

  return (
    <div className="space-y-5">

      {/* ── Upload Zone ── */}
      <div className="rounded-xl bg-white border border-slate-200 p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-sm font-bold text-slate-800">Source Documents</h3>
            <p className="text-xs text-slate-500 mt-0.5">Upload the ISO standard PDF or DOCX files to extract clauses from.</p>
          </div>
          {isEditable && (
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading || buildRunning}
              className="flex items-center gap-2 text-xs font-semibold text-amber-700 bg-amber-50 hover:bg-amber-100 border border-amber-200 rounded-lg px-3 py-2 transition-colors disabled:opacity-50"
            >
              {uploading ? <Spinner size="sm" /> : (
                <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                </svg>
              )}
              {uploading ? 'Uploading…' : 'Upload File'}
            </button>
          )}
          <input ref={fileInputRef} type="file" accept=".pdf,.docx,.doc" multiple className="hidden" onChange={handleFileInput} />
        </div>

        {/* Drop zone / file list */}
        {isEditable && sourceDocs.length === 0 ? (
          <div
            onDragOver={e => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`cursor-pointer border-2 border-dashed rounded-xl p-10 text-center transition-colors ${dragOver ? 'border-amber-400 bg-amber-50' : 'border-slate-200 hover:border-amber-300 hover:bg-amber-50/40'}`}
          >
            <div className="flex justify-center mb-3">
              <svg xmlns="http://www.w3.org/2000/svg" className="w-10 h-10 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m6.75 12l-3-3m0 0l-3 3m3-3v6m-1.5-15H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
              </svg>
            </div>
            <p className="text-sm font-semibold text-slate-600">Drop PDF or DOCX here</p>
            <p className="text-xs text-slate-400 mt-1">or click to browse — up to 100 MB per file</p>
          </div>
        ) : (
          <div
            onDragOver={e => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            className={`rounded-xl border-2 border-dashed transition-colors ${dragOver ? 'border-amber-400 bg-amber-50' : 'border-transparent'}`}
          >
            <ul className="space-y-2">
              {sourceDocs.map((doc, i) => (
                <li key={doc.gridfs_id ?? i} className="flex items-center gap-3 rounded-lg bg-slate-50 border border-slate-100 px-4 py-3">
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5 text-amber-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                  </svg>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-slate-800 truncate">{doc.filename}</p>
                    <p className="text-[10px] text-slate-400">Document #{i + 1}</p>
                  </div>
                  <span className="text-[10px] font-semibold text-green-600 bg-green-50 rounded-full px-2 py-0.5 flex-shrink-0">Ready</span>
                  {isEditable && !buildRunning && (
                    <button
                      onClick={() => handleRemoveDoc(doc.gridfs_id, doc.filename)}
                      disabled={removingDoc === doc.gridfs_id}
                      className="ml-1 p-1 rounded text-slate-400 hover:text-red-500 hover:bg-red-50 transition-colors disabled:opacity-40 flex-shrink-0"
                      title="Remove document"
                    >
                      {removingDoc === doc.gridfs_id
                        ? <Spinner size="sm" />
                        : <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
                      }
                    </button>
                  )}
                </li>
              ))}
              {uploading && (
                <li className="flex items-center gap-3 rounded-lg bg-amber-50 border border-amber-200 px-4 py-3">
                  <Spinner size="sm" />
                  <span className="text-sm text-amber-700">Uploading…</span>
                </li>
              )}
            </ul>
            {isEditable && !buildRunning && (
              <p className="text-xs text-slate-400 text-center mt-2 pb-1">Drop more files here to add them</p>
            )}
          </div>
        )}
      </div>

      {/* ── Build Trigger ── */}
      {isEditable && sourceDocs.length > 0 && (
        <div className="rounded-xl bg-white border border-slate-200 p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="text-sm font-bold text-slate-800">AI Extraction Pipeline</h3>
              <p className="text-xs text-slate-500 mt-1 max-w-lg">
                Multi-stage LangGraph pipeline: parses documents → detects clause structure → extracts each clause in parallel →
                verifier agent re-extracts any missed clauses (up to 2 loops) → embeds and saves all clauses as a draft.
              </p>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              {buildRunning && (
                <button
                  onClick={handleReset}
                  disabled={resetting}
                  className="flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50 transition-colors"
                  title="Clear stuck build so you can restart"
                >
                  {resetting ? <Spinner size="sm" /> : (
                    <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
                    </svg>
                  )}
                  Reset
                </button>
              )}
              <button
                onClick={handleBuild}
                disabled={building || buildRunning}
                className="flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-semibold text-white hover:bg-amber-600 disabled:opacity-50 transition-colors"
              >
                {building || buildRunning ? <Spinner size="sm" /> : (
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.348a1.125 1.125 0 010 1.971l-11.54 6.347a1.125 1.125 0 01-1.667-.986V5.653z" />
                  </svg>
                )}
                {buildRunning ? 'Building…' : 'Start AI Build'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Live Build Progress ── */}
      {buildJobId && (
        <div className="rounded-xl bg-white border border-slate-200 overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-3 border-b border-slate-100 bg-slate-50">
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full flex-shrink-0 ${
                isPaused ? 'bg-amber-400' :
                buildStatus === 'pause_requested' ? 'bg-amber-400 animate-pulse' :
                isConnected ? 'bg-green-400 animate-pulse' :
                jobStatus === 'done' ? 'bg-green-500' :
                jobStatus === 'failed' ? 'bg-red-500' :
                'bg-slate-300'
              }`} />
              <span className="text-xs font-semibold text-slate-700">
                {isPaused ? 'Build paused — checkpoint saved' :
                 buildStatus === 'pause_requested' ? 'Pause requested — finishing current batch…' :
                 isConnected ? 'Build running…' :
                 jobStatus === 'done' ? `Complete — ${finalClauseCount ?? extractedClauses.length} clauses extracted` :
                 jobStatus === 'failed' ? 'Build failed' :
                 'Waiting for worker…'}
              </span>
            </div>
            <div className="flex items-center gap-2">
              {/* Pause button — shown while actively running */}
              {buildRunning && !isPaused && buildStatus !== 'pause_requested' && (
                <button
                  onClick={handlePause}
                  disabled={pausing}
                  className="flex items-center gap-1.5 text-xs font-semibold text-amber-700 bg-amber-50 hover:bg-amber-100 border border-amber-200 rounded-md px-2.5 py-1.5 transition-colors disabled:opacity-50"
                  title="Pause after current batch"
                >
                  {pausing ? <Spinner size="sm" /> : (
                    <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>
                    </svg>
                  )}
                  Pause
                </button>
              )}
              {/* Resume button — shown when paused */}
              {isPaused && isEditable && (
                <button
                  onClick={handleResume}
                  disabled={resuming}
                  className="flex items-center gap-1.5 text-xs font-semibold text-green-700 bg-green-50 hover:bg-green-100 border border-green-200 rounded-md px-2.5 py-1.5 transition-colors disabled:opacity-50"
                >
                  {resuming ? <Spinner size="sm" /> : (
                    <svg xmlns="http://www.w3.org/2000/svg" className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M8 5v14l11-7z"/>
                    </svg>
                  )}
                  Resume
                </button>
              )}
              <span className="font-mono text-[10px] text-slate-400">{buildJobId.slice(0, 12)}…</span>
            </div>
          </div>

          <div className="p-5 space-y-5">
            {/* Pipeline stage tracker */}
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Pipeline Stages</p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {stages.map(({ key, status: s }) => (
                  <StageIndicator key={key} stageKey={key} stageStatus={s} />
                ))}
              </div>
            </div>

            {/* Extracted clauses live list */}
            {extractedClauses.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
                  Extracted Clauses <span className="text-amber-600 font-bold">({extractedClauses.length})</span>
                </p>
                <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
                  {extractedClauses.map(cid => (
                    <span key={cid} className="text-xs font-mono bg-green-50 text-green-700 border border-green-200 rounded px-2 py-0.5">{cid}</span>
                  ))}
                </div>
              </div>
            )}

            {/* Detail log */}
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Live Log</p>
              <div
                ref={logRef}
                className="bg-slate-950 rounded-xl p-4 font-mono text-xs h-56 overflow-y-auto space-y-1"
              >
                {logMessages.length === 0 ? (
                  <p className="text-slate-600">Waiting for pipeline output…</p>
                ) : logMessages.map((msg, i) => {
                  const stage = msg.stage ?? 'info'
                  const detail = msg.detail ?? msg.message ?? JSON.stringify(msg)
                  const stageColors = {
                    parse: 'text-blue-400', structure: 'text-purple-400', detect_structure: 'text-purple-400',
                    extract: 'text-indigo-400', extract_clauses: 'text-indigo-400',
                    verify: 'text-orange-400', verify_coverage: 'text-orange-400',
                    template: 'text-teal-400', gen_state_template: 'text-teal-400',
                    persist: 'text-green-400', complete: 'text-green-300',
                  }
                  const color = stageColors[stage] ?? 'text-slate-400'
                  const textColor = msg.status === 'failed' ? 'text-red-400' : msg.status === 'done' ? 'text-green-300' : 'text-slate-200'
                  return (
                    <div key={i} className="leading-relaxed">
                      <span className={`${color} mr-2 font-semibold`}>[{stage}]</span>
                      <span className={textColor}>{detail}</span>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Completion banners */}
            {jobStatus === 'done' && (
              <div className="rounded-xl bg-green-50 border border-green-200 px-5 py-4">
                <p className="text-sm font-bold text-green-800">Build complete!</p>
                <p className="text-xs text-green-700 mt-0.5">
                  {finalClauseCount ?? extractedClauses.length} clauses extracted and saved as draft.
                  Switch to the <strong>Clauses</strong> tab to review and edit them before publishing.
                </p>
              </div>
            )}
            {isPaused && (
              <div className="rounded-xl bg-amber-50 border border-amber-200 px-5 py-4">
                <p className="text-sm font-bold text-amber-800">Build paused</p>
                <p className="text-xs text-amber-700 mt-0.5">
                  Progress has been checkpointed. Click <strong>Resume</strong> above to continue from where it left off —
                  already-extracted clauses will be skipped.
                </p>
              </div>
            )}
            {jobStatus === 'failed' && (
              <div className="rounded-xl bg-red-50 border border-red-200 px-5 py-4">
                <p className="text-sm font-bold text-red-800">Build failed</p>
                <p className="text-xs text-red-700 mt-0.5">Check the log above for details. You can click <strong>Start AI Build</strong> again to retry.</p>
              </div>
            )}
          </div>
        </div>
      )}

      {!isEditable && (
        <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-3 text-xs text-slate-500">
          This version is <strong>{version.status}</strong>. Build operations are only available on draft versions.
        </div>
      )}
    </div>
  )
}

// ─── Main Page ───────────────────────────────────────────────────────────────

const TABS = ['Clauses', 'Template', 'Build']

export default function AdminVersionDetailPage() {
  const { vid } = useParams()
  const navigate = useNavigate()
  const [version, setVersion] = useState(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('Clauses')
  const [actionBusy, setActionBusy] = useState(false)

  async function refreshVersion() {
    const data = await getVersion(vid).catch(() => null)
    setVersion(data)
  }

  useEffect(() => {
    refreshVersion().finally(() => setLoading(false))
  }, [vid])

  async function handleStatusAction(action) {
    setActionBusy(true)
    try {
      if (action === 'publish') await publishVersion(vid)
      else if (action === 'archive') await archiveVersion(vid)
      await refreshVersion()
    } catch (err) {
      alert(err.message)
    } finally {
      setActionBusy(false)
    }
  }

  if (loading) return <div className="flex justify-center py-20"><Spinner size="lg" /></div>
  if (!version) return (
    <div className="text-center py-20">
      <p className="text-slate-500 text-sm">Version not found.</p>
      <button onClick={() => navigate('/admin/versions')} className="mt-3 text-xs text-amber-600 hover:underline">← Back to versions</button>
    </div>
  )

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      {/* Header */}
      <div className="rounded-xl bg-white border border-slate-200 border-l-4 border-l-amber-400 shadow-sm p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <button onClick={() => navigate('/admin/versions')} className="text-xs text-slate-400 hover:text-amber-600 mb-1 transition-colors">
              ← ISO Versions
            </button>
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-xl font-bold text-slate-900">{version.name}</h1>
              <StatusBadge status={version.status} />
              <span className="font-mono text-xs bg-slate-100 text-slate-500 rounded px-1.5 py-0.5">{version.version_id}</span>
            </div>
            <p className="text-sm text-slate-500 mt-1">
              {version.clause_count ?? 0} clauses · {version.source} source
              {version.description && ` · ${version.description}`}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {version.status === 'draft' && (
              <button
                onClick={() => handleStatusAction('publish')}
                disabled={actionBusy}
                className="flex items-center gap-2 rounded-lg bg-green-600 px-3 py-2 text-xs font-semibold text-white hover:bg-green-700 disabled:opacity-50 transition-colors"
              >
                {actionBusy ? <Spinner size="sm" /> : null} Publish
              </button>
            )}
            {version.status === 'published' && (
              <button
                onClick={() => handleStatusAction('archive')}
                disabled={actionBusy}
                className="flex items-center gap-2 rounded-lg bg-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-300 disabled:opacity-50 transition-colors"
              >
                {actionBusy ? <Spinner size="sm" /> : null} Archive
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-200">
        {TABS.map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-5 py-3 text-sm font-semibold border-b-2 transition-colors ${
              tab === t
                ? 'border-amber-500 text-amber-700'
                : 'border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === 'Clauses' && <ClausesTab vid={vid} version={version} />}
      {tab === 'Template' && <TemplateTab vid={vid} version={version} />}
      {tab === 'Build' && <BuildTab vid={vid} version={version} onVersionUpdated={refreshVersion} />}
    </div>
  )
}
