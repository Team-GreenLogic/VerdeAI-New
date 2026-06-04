import { useState, useEffect, useRef, useCallback } from 'react'
import { apiPost } from '../api/client.js'

const WS_URL = import.meta.env.VITE_API_URL?.replace('http', 'ws') || 'ws://localhost:8000'
const TERMINAL = new Set(['done', 'failed', 'deduped'])
const MAX_RETRIES = 3

/**
 * Subscribe to WebSocket job progress events.
 * @param {string|null} jobId - job/analysis/document id to track
 * @param {object} opts
 * @param {function} [opts.onThinkingToken] - called directly for each thinking_token event,
 *   bypassing the messages array to avoid O(n²) re-renders on large token streams.
 * @returns {{ messages, status, isConnected }}
 */
export function useJobProgress(jobId, { onThinkingToken } = {}) {
  const [messages, setMessages] = useState([])
  const [status, setStatus] = useState(null)
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef(null)
  const retriesRef = useRef(0)
  const activeRef = useRef(true)
  // Keep a stable ref to the callback so the WS handler always calls the latest version
  const onThinkingTokenRef = useRef(onThinkingToken)
  useEffect(() => { onThinkingTokenRef.current = onThinkingToken }, [onThinkingToken])

  // Synchronous copy of status so onclose can check terminal state without
  // racing with React's async state batching (ws.close() fires onclose sync).
  const statusRef = useRef(status)
  useEffect(() => { statusRef.current = status }, [status])

  const connect = useCallback(async () => {
    if (!jobId || !activeRef.current) return
    // Clear messages on reconnect so the server's history replay produces
    // a clean state (no duplicate clause entries from the previous connection).
    setMessages([])
    try {
      const { ticket } = await apiPost('/ws/ticket')
      if (!activeRef.current) return

      const ws = new WebSocket(`${WS_URL}/ws/jobs/${jobId}?ticket=${ticket}`)
      wsRef.current = ws

      ws.onopen = () => {
        setIsConnected(true)
      }

      ws.onmessage = (e) => {
        try {
          const payload = JSON.parse(e.data)

          // Route thinking_token events directly to the callback — never put them
          // in the messages array. This keeps messages small so useMemo stays O(n)
          // and clause completion events render immediately without lag.
          if (payload.stage === 'thinking_token') {
            onThinkingTokenRef.current?.(payload)
            return
          }

          setMessages((prev) => [...prev, payload])
          if (payload.status && TERMINAL.has(payload.status)) {
            // Update ref synchronously so onclose (fired by ws.close() below)
            // sees the terminal status and skips retry.
            statusRef.current = payload.status
            setStatus(payload.status)
            ws.close()
          }
        } catch (_) {}
      }

      ws.onclose = () => {
        setIsConnected(false)
        // Don't retry if we already received a terminal status
        if (statusRef.current && TERMINAL.has(statusRef.current)) return
        if (activeRef.current && retriesRef.current < MAX_RETRIES) {
          retriesRef.current++
          setTimeout(connect, 2000)
        }
      }

      ws.onerror = () => ws.close()
    } catch (_) {
      if (activeRef.current && retriesRef.current < MAX_RETRIES) {
        retriesRef.current++
        setTimeout(connect, 2000)
      }
    }
  }, [jobId])

  useEffect(() => {
    if (!jobId) return
    activeRef.current = true
    retriesRef.current = 0
    setMessages([])
    setStatus(null)
    connect()
    return () => {
      activeRef.current = false
      wsRef.current?.close()
    }
  }, [jobId, connect])

  return { messages, status, isConnected }
}
