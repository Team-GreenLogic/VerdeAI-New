import { apiGet, apiPostForm, apiDelete } from './client.js'

export async function uploadDocument(file) {
  const form = new FormData()
  form.append('file', file)
  return apiPostForm('/documents', form)
}

export async function listDocuments() {
  return apiGet('/documents')
}

export async function getDocument(id) {
  return apiGet(`/documents/${id}`)
}

export async function deleteDocument(id) {
  return apiDelete(`/documents/${id}`)
}
