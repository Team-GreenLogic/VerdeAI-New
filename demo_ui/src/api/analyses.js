import { apiGet, apiPost, apiDelete, apiGetBlob } from './client.js'

export async function getVersions() {
  return apiGet('/analyses/versions')
}

export async function createAnalysis(profileId, scope = 'full', versionId = 'iso-14001-2015') {
  return apiPost('/analyses', { profile_id: profileId, scope, version_id: versionId })
}

export async function listAnalyses(profileId) {
  const qs = profileId ? `?profile_id=${encodeURIComponent(profileId)}` : ''
  return apiGet(`/analyses${qs}`)
}

export async function getAnalysis(id) {
  return apiGet(`/analyses/${id}`)
}

export async function deleteAnalysis(id) {
  return apiDelete(`/analyses/${id}`)
}

export async function pauseAnalysis(id) {
  return apiPost(`/analyses/${id}/pause`)
}

export async function resumeAnalysis(id) {
  return apiPost(`/analyses/${id}/resume`)
}

export async function getResults(id) {
  return apiGet(`/analyses/${id}/results`)
}

export async function getRecommendations(id, { sortBy, order } = {}) {
  const params = new URLSearchParams()
  if (sortBy) params.set('sort_by', sortBy)
  if (order) params.set('order', order)
  const qs = params.toString() ? `?${params.toString()}` : ''
  return apiGet(`/analyses/${id}/recommendations${qs}`)
}

export async function getMissingRequirements(id) {
  return apiGet(`/analyses/${id}/missing-requirements`)
}

export async function downloadReport(id) {
  return apiGetBlob(`/analyses/${id}/report.pdf`)
}

export async function getStaleness(id) {
  return apiGet(`/analyses/${id}/staleness`)
}

export async function reanalyzeDelta(id) {
  return apiPost(`/analyses/${id}/reanalyze-delta`)
}
