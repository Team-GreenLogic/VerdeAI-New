import { apiPost } from './client.js'

export async function login(email, password) {
  const data = await apiPost('/auth/login', { email, password })
  localStorage.setItem('access_token', data.access_token)
  localStorage.setItem('refresh_token', data.refresh_token)
  return data
}

export async function register(email, password, firstName, lastName, organisationName) {
  return apiPost('/auth/register', {
    email,
    password,
    first_name: firstName,
    last_name: lastName,
    organisation_name: organisationName,
  })
}

export function logout() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
}

export function isLoggedIn() {
  return !!localStorage.getItem('access_token')
}
