import { apiGet, apiPost, apiPut, apiDelete } from './client.js'

export async function listProfiles() {
  return apiGet('/org-profiles')
}

export async function createProfile(fields) {
  return apiPost('/org-profiles', fields)
}

export async function getProfile(profileId) {
  return apiGet(`/org-profiles/${profileId}`)
}

export async function updateProfile(profileId, fields) {
  return apiPut(`/org-profiles/${profileId}`, fields)
}

export async function deleteProfile(profileId) {
  return apiDelete(`/org-profiles/${profileId}`)
}

export async function getCompleteness(profileId) {
  return apiGet(`/org-profiles/${profileId}/completeness`)
}

export async function listClauses(profileId) {
  return apiGet(`/org-profiles/${profileId}/clauses`)
}

export async function getClause(profileId, clauseId) {
  return apiGet(`/org-profiles/${profileId}/clauses/${clauseId}`)
}

export async function updateClause(profileId, clauseId, data) {
  return apiPut(`/org-profiles/${profileId}/clauses/${clauseId}`, data)
}

