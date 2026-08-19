import { apiGet, apiPostForm, apiDelete } from './client.js'

export async function uploadDocument(file, profileId) {
  const form = new FormData()
  form.append('file', file)
  return apiPostForm(`/documents?profile_id=${encodeURIComponent(profileId)}`, form)
}

export async function listDocuments(profileId) {
  const qs = profileId ? `?profile_id=${encodeURIComponent(profileId)}` : ''
  return apiGet(`/documents${qs}`)
}

export async function getDocument(id) {
  return apiGet(`/documents/${id}`)
}

export async function deleteDocument(id) {
  return apiDelete(`/documents/${id}`)
}
