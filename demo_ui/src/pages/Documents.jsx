import { useEffect, useState, useRef } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { uploadDocument, listDocuments, deleteDocument } from '../api/documents.js'
import { getProfile } from '../api/orgProfiles.js'
import { useJobProgress } from '../hooks/useJobProgress.js'
import Badge from '../components/Badge.jsx'
import Spinner from '../components/Spinner.jsx'

const UploadSVG = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.338-2.32 5.75 5.75 0 011.021 8.266A3.5 3.5 0 0115 19.5H6.75z" />
  </svg>
)

const InboxSVG = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-12 h-12" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 13.5h3.86a2.25 2.25 0 012.012 1.244l.256.512a2.25 2.25 0 002.013 1.244h3.218a2.25 2.25 0 002.013-1.244l.256-.512a2.25 2.25 0 012.013-1.244h3.859m-19.5.338V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18v-4.162c0-.224-.034-.447-.1-.661L19.24 5.338a2.25 2.25 0 00-2.15-1.588H6.911a2.25 2.25 0 00-2.15 1.588L2.35 13.177a2.25 2.25 0 00-.1.661z" />
  </svg>
)

function ProgressPanel({ jobId, filename, onDone }) {
  const { messages, status, isConnected } = useJobProgress(jobId)

  useEffect(() => {
    if (status === 'done' || status === 'deduped' || status === 'failed') {
      onDone()
    }
  }, [status, onDone])

  return (
    <div className="rounded-xl bg-white border border-slate-200 shadow-sm p-4 mb-4">
      <div className="flex items-center gap-2 mb-3">
        {!status && <Spinner size="sm" />}
        <span className="text-sm font-semibold text-slate-700 truncate flex-1">
          {filename}
        </span>
        {status ? <Badge status={status} /> : (
          <span className="text-xs text-slate-400">{isConnected ? 'Processing…' : 'Connecting…'}</span>
        )}
      </div>
      <div className="max-h-28 overflow-y-auto space-y-1 scrollbar-thin bg-slate-900 rounded-lg p-3">
        {messages.map((m, i) => (
          <p key={i} className="text-xs text-emerald-300 font-mono">
            [{m.stage}] {m.detail}
          </p>
        ))}
        {messages.length === 0 && (
          <p className="text-xs text-slate-500 font-mono">Waiting for progress…</p>
        )}
      </div>
    </div>
  )
}

export default function Documents() {
  const { profileId } = useParams()
  const navigate = useNavigate()
  const [profile, setProfile] = useState(null)
  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [activeJobs, setActiveJobs] = useState([])
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef()

  useEffect(() => {
    getProfile(profileId).then(setProfile).catch(() => setProfile(null))
  }, [profileId])

  async function refresh() {
    const data = await listDocuments(profileId).catch(() => [])
    const items = Array.isArray(data) ? data : data?.items || []
    setDocs(items.filter(doc => doc.status !== 'deleted'))
  }

  useEffect(() => {
    async function init() {
      setLoading(true)
      try {
        const data = await listDocuments(profileId).catch(() => ({ items: [] }))
        const items = (Array.isArray(data) ? data : data?.items || []).filter(doc => doc.status !== 'deleted')
        setDocs(items)

        // Recover any jobs that were still processing before a page reload.
        const TERMINAL = new Set(['ready', 'failed', 'deduped', 'deleted'])
        const recovering = items
          .filter(doc => !TERMINAL.has(doc.status))
          .map(doc => ({ jobId: doc.document_id, filename: doc.filename }))
        if (recovering.length > 0) {
          setActiveJobs(recovering)
        }
      } finally {
        setLoading(false)
      }
    }
    init()
  }, [profileId])

  async function handleFiles(fileList) {
    const files = Array.from(fileList || [])
    if (files.length === 0) return
    setUploading(true)
    // Sequential rather than parallel: each upload kicks off its own processing
    // job, and one rejected file shouldn't abort the rest of the batch.
    const failed = []
    try {
      for (const file of files) {
        try {
          const res = await uploadDocument(file, profileId)
          setActiveJobs(j => [...j, { jobId: res.document_id, filename: file.name }])
        } catch (err) {
          failed.push(`${file.name}: ${err.message}`)
        }
      }
    } finally {
      setUploading(false)
    }
    if (failed.length > 0) {
      alert(`Upload failed for ${failed.length} of ${files.length} file(s):\n\n${failed.join('\n')}`)
    }
  }

  function handleDrop(e) {
    e.preventDefault()
    setDragOver(false)
    handleFiles(e.dataTransfer.files)
  }

  async function handleFileInput(e) {
    await handleFiles(e.target.files)
    e.target.value = ''  // allow re-selecting the same file
  }

  async function handleDelete(id) {
    if (!confirm('Delete this document?')) return
    try {
      await deleteDocument(id)
      await refresh()
    } catch (err) {
      alert(err.message)
    }
  }

  function handleJobDone(jobId) {
    setActiveJobs(j => j.filter(x => x.jobId !== jobId))
    refresh()
  }

  const FORMATS = ['PDF', 'DOCX', 'TXT', 'XLSX', 'PPTX']

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <button onClick={() => navigate('/documents')} className="text-xs text-slate-400 hover:text-brand-600 mb-1 transition-colors">
          ← Documents
        </button>
        <h1 className="text-2xl font-bold text-slate-900">
          {profile?.org_name || 'Documents'}
        </h1>
        <p className="text-sm text-slate-500 mt-1">Upload compliance evidence documents for analysis</p>
      </div>

      {/* Upload zone */}
      <div
        onDrop={handleDrop}
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onClick={() => fileRef.current?.click()}
        className={`cursor-pointer rounded-xl border-2 border-dashed p-10 text-center transition-all ${
          dragOver ? 'border-brand-500 bg-brand-50' : 'border-slate-200 hover:border-brand-400 hover:bg-slate-50'
        }`}
      >
        <input
          ref={fileRef}
          type="file"
          className="hidden"
          multiple
          accept=".pdf,.docx,.txt,.xlsx,.pptx"
          onChange={handleFileInput}
        />
        {uploading ? (
          <div className="flex flex-col items-center gap-3">
            <Spinner size="lg" />
            <p className="text-sm text-slate-500">Uploading…</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <span className="text-slate-300">
              <UploadSVG />
            </span>
            <div>
              <p className="text-sm font-semibold text-slate-700">Drop files here or click to upload</p>
              <p className="text-xs text-slate-400 mt-1">Multiple files supported · Max 100 MB each</p>
            </div>
            <div className="flex gap-1.5 flex-wrap justify-center">
              {FORMATS.map(f => (
                <span key={f} className="rounded-full bg-slate-100 text-slate-500 text-xs px-2 py-0.5 font-medium">{f}</span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Active jobs */}
      {activeJobs.map(({ jobId, filename }) => (
        <ProgressPanel
          key={jobId}
          jobId={jobId}
          filename={filename}
          onDone={() => handleJobDone(jobId)}
        />
      ))}

      {/* Documents table */}
      {loading ? (
        <div className="flex justify-center py-10"><Spinner size="lg" /></div>
      ) : docs.length === 0 ? (
        <div className="rounded-xl bg-white border border-slate-200 p-12 text-center">
          <div className="flex justify-center text-slate-300 mb-3">
            <InboxSVG />
          </div>
          <p className="text-sm font-semibold text-slate-600">No documents yet</p>
          <p className="text-xs text-slate-400 mt-1">Upload your first document to get started.</p>
        </div>
      ) : (
        <div className="rounded-xl bg-white border border-slate-200 shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Filename</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Status</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Pages</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Uploaded</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {docs.map(doc => {
                const matchFilename = doc.previous_version_id
                  ? docs.find(d => d.document_id === doc.previous_version_id)?.filename
                  : null
                return (
                <tr key={doc.document_id} className="hover:bg-brand-50/40 transition-colors">
                  <td className="px-4 py-3 font-medium text-slate-800 max-w-xs">
                    <div className="truncate">{doc.filename}</div>
                    {doc.previous_version_id && doc.cdc_overlap != null && (
                      <span
                        title={`${Math.round(doc.cdc_overlap * 100)}% byte-overlap with ${matchFilename ?? 'a previous document'} — treated as a modified version.`}
                        className="mt-1 inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700 max-w-full"
                      >
                        <span className="truncate">{Math.round(doc.cdc_overlap * 100)}% match · {matchFilename ?? 'previous version'}</span>
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3"><Badge status={doc.status} /></td>
                  <td className="px-4 py-3 text-slate-500">{doc.pages ?? '—'}</td>
                  <td className="px-4 py-3 text-slate-400 text-xs">
                    {new Date(doc.uploaded_at || doc.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => handleDelete(doc.document_id)}
                      className="text-xs font-medium text-slate-400 hover:text-red-500 border border-slate-200 hover:border-red-200 rounded-md px-2 py-1 transition-colors"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
