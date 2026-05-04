import { apiGet, apiPost } from './client.js'

export async function createAnalysis(scope = 'full') {
  return apiPost('/analyses', { scope })
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
