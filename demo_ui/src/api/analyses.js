import { apiGet, apiPost, apiGetBlob } from './client.js'

export async function getVersions() {
  return apiGet('/analyses/versions')
}

export async function createAnalysis(scope = 'full', versionId = 'iso-14001-2015') {
  return apiPost('/analyses', { scope, version_id: versionId })
}

export async function listAnalyses() {
  return apiGet('/analyses')
}

export async function getAnalysis(id) {
  return apiGet(`/analyses/${id}`)
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

export async function getRecommendations(id) {
  return apiGet(`/analyses/${id}/recommendations`)
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
