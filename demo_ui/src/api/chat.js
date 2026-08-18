import { apiDelete, apiGet, apiPost } from './client.js'

const CHAT_URL = import.meta.env.VITE_CHAT_URL

export async function createSession() {
  return apiPost('/chat/session', {}, { chat: true })
}

/** List this tenant's past chat sessions, most recently active first. */
export async function listSessions() {
  return apiGet('/chat/sessions', { chat: true })
}

/** Full message history for one session, for resuming a past conversation. */
export async function getSessionMessages(sessionId) {
  return apiGet(`/chat/sessions/${sessionId}/messages`, { chat: true })
}

export async function deleteSession(sessionId) {
  return apiDelete(`/chat/sessions/${sessionId}`, { chat: true })
}

/**
 * Stream a chat response via SSE (POST + fetch ReadableStream).
 * @param {string} question
 * @param {string|null} sessionId
 * @param {function} onToken  - called with each text token string
 * @param {function} onCitations - called with citations array
 * @param {function} onDone  - called when stream ends successfully
 * @param {function} onError - called with error message string
 * @returns {AbortController} - call .abort() to cancel
 */
export function streamChat(question, sessionId, onToken, onCitations, onDone, onError) {
  const controller = new AbortController()
  const token = localStorage.getItem('access_token')

  // Safety wrapper — ensures onDone() is called exactly once even if the
  // server closes the connection without sending a "done" SSE event.
  let doneCalled = false
  const safeDone = () => { if (!doneCalled) { doneCalled = true; onDone() } }

  fetch(`${CHAT_URL}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ question, session_id: sessionId }),
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok) {
        onError(`HTTP ${res.status}`)
        safeDone()
        return
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // Split on \r\n\r\n or \n\n — sse-starlette uses CRLF line endings
        const frames = buffer.split(/\r?\n\r?\n/)
        buffer = frames.pop() // keep incomplete frame

        for (const frame of frames) {
          const dataLine = frame
            .split('\n')
            .find((l) => l.startsWith('data:'))
          if (!dataLine) continue
          const raw = dataLine.slice(5).trim()
          let event
          try { event = JSON.parse(raw) } catch (_) { continue }
          console.debug('[chat] event:', event)

          if (event.type === 'token') {
            onToken(event.content)
            // Yield to the macrotask queue so React renders each token
            // individually, producing a natural typing effect.
            await new Promise((r) => setTimeout(r, 0))
          } else if (event.type === 'citations') {
            onCitations(event.citations || [])
          } else if (event.type === 'error') {
            onError(event.content)
          } else if (event.type === 'done') {
            safeDone()
          }
        }
      }
      // Ensure loading stops if the stream closes without a "done" event
      safeDone()
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onError(err.message)
        safeDone()
      }
    })

  return controller
}
