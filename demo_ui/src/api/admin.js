import { apiGet, apiPost, apiPut, apiDelete, apiPostForm } from './client.js'

// Versions
export const listVersions = () => apiGet('/admin/versions')
export const createVersion = (body) => apiPost('/admin/versions', body)
export const getVersion = (vid) => apiGet(`/admin/versions/${vid}`)
export const deleteVersion = (vid) => apiDelete(`/admin/versions/${vid}`)
export const publishVersion = (vid) => apiPost(`/admin/versions/${vid}/publish`)
export const archiveVersion = (vid) => apiPost(`/admin/versions/${vid}/archive`)

// Clauses within a version
export const listClauses = (vid) => apiGet(`/admin/versions/${vid}/clauses`)
export const getClause = (vid, cid) => apiGet(`/admin/versions/${vid}/clauses/${cid}`)
export const createClause = (vid, body) => apiPost(`/admin/versions/${vid}/clauses`, body)
export const updateClause = (vid, cid, body) => apiPut(`/admin/versions/${vid}/clauses/${cid}`, body)
export const deleteClause = (vid, cid) => apiDelete(`/admin/versions/${vid}/clauses/${cid}`)

// Template
export const getClauseTemplate = (vid, cid) => apiGet(`/admin/versions/${vid}/clauses/${cid}/template`)
export const updateClauseTemplate = (vid, cid, fields) =>
  apiPut(`/admin/versions/${vid}/clauses/${cid}/template`, { fields })

// AI Build
export const uploadSourceDoc = (vid, formData) => apiPostForm(`/admin/versions/${vid}/documents`, formData)
export const deleteSourceDoc = (vid, gridfsId) => apiDelete(`/admin/versions/${vid}/documents/${gridfsId}`)
export const triggerBuild = (vid) => apiPost(`/admin/versions/${vid}/build`)
export const pauseBuild = (vid) => apiPost(`/admin/versions/${vid}/build/pause`)
export const resumeBuild = (vid) => apiPost(`/admin/versions/${vid}/build/resume`)
export const resetBuild = (vid) => apiPost(`/admin/versions/${vid}/build/reset`)
