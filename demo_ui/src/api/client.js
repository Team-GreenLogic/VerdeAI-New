const API_URL = import.meta.env.VITE_API_URL
const CHAT_URL = import.meta.env.VITE_CHAT_URL

function getToken() {
  return localStorage.getItem('access_token')
}

function authHeaders(extra = {}) {
  const token = getToken()
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...extra,
  }
}

async function handleResponse(res) {
  if (res.status === 401) {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      detail = body.detail || JSON.stringify(body)
    } catch (_) {}
    throw new Error(detail)
  }
  const text = await res.text()
  return text ? JSON.parse(text) : null
}

export async function apiGet(path, { chat = false } = {}) {
  const base = chat ? CHAT_URL : API_URL
  const res = await fetch(`${base}${path}`, {
    headers: authHeaders(),
  })
  return handleResponse(res)
}

export async function apiGetBlob(path, { chat = false } = {}) {
  const base = chat ? CHAT_URL : API_URL
  const res = await fetch(`${base}${path}`, {
    headers: authHeaders(),
  })
  if (res.status === 401) {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch (_) {}
    throw new Error(detail)
  }
  return res.blob()
}

export async function apiPost(path, body = null, { chat = false } = {}) {
  const base = chat ? CHAT_URL : API_URL
  const res = await fetch(`${base}${path}`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: body !== null ? JSON.stringify(body) : undefined,
  })
  return handleResponse(res)
}

export async function apiPut(path, body = null, { chat = false } = {}) {
  const base = chat ? CHAT_URL : API_URL
  const res = await fetch(`${base}${path}`, {
    method: 'PUT',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: body !== null ? JSON.stringify(body) : undefined,
  })
  return handleResponse(res)
}

export async function apiDelete(path, { chat = false } = {}) {
  const base = chat ? CHAT_URL : API_URL
  const res = await fetch(`${base}${path}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  return handleResponse(res)
}

export async function apiPostForm(path, formData) {
  const res = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: authHeaders(),
    body: formData,
  })
  return handleResponse(res)
}
