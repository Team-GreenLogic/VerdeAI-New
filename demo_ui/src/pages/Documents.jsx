import { useEffect, useState, useRef } from 'react'
import { uploadDocument, listDocuments, deleteDocument } from '../api/documents.js'
import { useJobProgress } from '../hooks/useJobProgress.js'
import Badge from '../components/Badge.jsx'
import Spinner from '../components/Spinner.jsx'

function ProgressPanel({ jobId, filename, onDone }) {
  const { messages, status, isConnected } = useJobProgress(jobId)

  useEffect(() => {
    if (status === 'done' || status === 'deduped' || status === 'failed') {
      onDone()
    }
  }, [status, onDone])

  return (
    <div className="rounded-xl border border-blue-100 bg-blue-50 p-4 mb-4">
      <div className="flex items-center gap-2 mb-2">
        {!status && <Spinner size="sm" />}
        <span className="text-sm font-semibold text-blue-800">
          Processing: {filename}
        </span>
        {status && <Badge status={status} />}
      </div>
      <div className="max-h-28 overflow-y-auto space-y-1 scrollbar-thin">
        {messages.map((m, i) => (
          <p key={i} className="text-xs text-blue-700">
            [{m.stage}] {m.detail}
          </p>
        ))}
        {messages.length === 0 && (
          <p className="text-xs text-blue-500">Waiting for progress…</p>
        )}
      </div>
    </div>
  )
}

export default function Documents() {
  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [activeJobs, setActiveJobs] = useState([]) // [{jobId, filename}]
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef()

  async function refresh() {
    const data = await listDocuments().catch(() => [])
    setDocs(Array.isArray(data) ? data : data?.items || [])
  }

  useEffect(() => {
    refresh().finally(() => setLoading(false))
  }, [])

  async function handleFiles(files) {
    const file = files[0]
    if (!file) return
    setUploading(true)
    try {
      const res = await uploadDocument(file)
      setActiveJobs(j => [...j, { jobId: res.document_id, filename: file.name }])
    } catch (err) {
      alert(err.message)
    } finally {
      setUploading(false)
    }
  }

  function handleDrop(e) {
    e.preventDefault()
    setDragOver(false)
    handleFiles(e.dataTransfer.files)
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

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Documents</h1>

      {/* Upload zone */}
      <div
        onDrop={handleDrop}
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onClick={() => fileRef.current?.click()}
        className={`cursor-pointer rounded-xl border-2 border-dashed p-10 text-center transition-colors ${
          dragOver ? 'border-brand-500 bg-brand-50' : 'border-gray-200 hover:border-brand-300'
        }`}
      >
        <input
          ref={fileRef}
          type="file"
          className="hidden"
          accept=".pdf,.docx,.txt,.xlsx,.pptx"
          onChange={e => handleFiles(e.target.files)}
        />
        {uploading ? (
          <div className="flex flex-col items-center gap-2">
            <Spinner size="lg" />
            <p className="text-sm text-gray-500">Uploading…</p>
          </div>
        ) : (
          <>
            <p className="text-3xl mb-2">📤</p>
            <p className="text-sm font-medium text-gray-700">Drop a file here or click to upload</p>
            <p className="text-xs text-gray-400 mt-1">PDF, DOCX, TXT, XLSX, PPTX — max 100 MB</p>
          </>
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
        <div className="rounded-xl bg-white border border-gray-100 p-10 text-center text-gray-400">
          <p className="text-3xl mb-2">📭</p>
          <p className="text-sm">No documents yet. Upload one to get started.</p>
        </div>
      ) : (
        <div className="rounded-xl bg-white border border-gray-100 shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Filename</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Status</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Pages</th>
                <th className="px-4 py-3 text-left font-medium text-gray-600">Uploaded</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {docs.map(doc => (
                <tr key={doc.document_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-800 max-w-xs truncate">
                    {doc.filename}
                  </td>
                  <td className="px-4 py-3"><Badge status={doc.status} /></td>
                  <td className="px-4 py-3 text-gray-500">{doc.pages ?? '—'}</td>
                  <td className="px-4 py-3 text-gray-400 text-xs">
                    {new Date(doc.uploaded_at || doc.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => handleDelete(doc.document_id)}
                      className="text-xs text-red-500 hover:text-red-700"
                    >
                      Delete
                    </button>
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
