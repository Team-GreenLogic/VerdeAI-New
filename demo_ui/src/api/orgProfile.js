import { apiGet, apiPut } from './client.js'

export async function getProfile() {
  return apiGet('/org-profile')
}

export async function updateProfile(fields) {
  return apiPut('/org-profile', fields)
}

export async function getCompleteness() {
  return apiGet('/org-profile/completeness')
}

export async function listClauses() {
  return apiGet('/org-profile/clauses')
}

export async function getClause(clauseId) {
  return apiGet(`/org-profile/clauses/${clauseId}`)
}

export async function updateClause(clauseId, data) {
  return apiPut(`/org-profile/clauses/${clauseId}`, data)
}
