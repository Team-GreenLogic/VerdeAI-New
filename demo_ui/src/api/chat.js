import { apiPost } from './client.js'

const CHAT_URL = import.meta.env.VITE_CHAT_URL

export async function createSession() {
  return apiPost('/chat/session', {}, { chat: true })
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
        onDone()
        return
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // Process complete SSE frames (split on double newline)
        const frames = buffer.split('\n\n')
        buffer = frames.pop() // keep incomplete frame

        for (const frame of frames) {
          const dataLine = frame
            .split('\n')
            .find((l) => l.startsWith('data:'))
          if (!dataLine) continue
          const raw = dataLine.slice(5).trim()
          try {
            const event = JSON.parse(raw)
            if (event.type === 'token') onToken(event.content)
            else if (event.type === 'citations') onCitations(event.citations || [])
            else if (event.type === 'error') onError(event.content)
            else if (event.type === 'done') onDone()
          } catch (_) {}
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onError(err.message)
        onDone()
      }
    })

  return controller
}
