import { apiGet, apiPost } from './client.js'

export function getRecommendationContext(profileId) {
  return apiGet(`/personalized-recommendations/context?profile_id=${encodeURIComponent(profileId)}`)
}

export function listPersonalizedRuns(profileId) {
  return apiGet(`/personalized-recommendations?profile_id=${encodeURIComponent(profileId)}`)
}

export function getPersonalizedRun(runId) {
  return apiGet(`/personalized-recommendations/${encodeURIComponent(runId)}`)
}

export function createPersonalizedRun(profileId) {
  return apiPost('/personalized-recommendations', { profile_id: profileId })
}
