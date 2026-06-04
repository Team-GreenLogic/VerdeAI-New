import { useState, useEffect, useRef, useCallback } from 'react'
import { apiPost } from '../api/client.js'

const WS_URL = import.meta.env.VITE_API_URL?.replace('http', 'ws') || 'ws://localhost:8000'
const TERMINAL = new Set(['done', 'failed', 'deduped', 'paused'])
const MAX_RETRIES = 3

/**
 * Subscribe to WebSocket job progress events.
 * @param {string|null} jobId - job/analysis/document id to track
 * @returns {{ messages, status, isConnected }}
 */
export function useJobProgress(jobId) {
  const [messages, setMessages] = useState([])
  const [status, setStatus] = useState(null)
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef(null)
  const retriesRef = useRef(0)
  const activeRef = useRef(true)

  const connect = useCallback(async () => {
    if (!jobId || !activeRef.current) return
    try {
      const { ticket } = await apiPost('/ws/ticket')
      if (!activeRef.current) return

      const ws = new WebSocket(`${WS_URL}/ws/jobs/${jobId}?ticket=${ticket}`)
      wsRef.current = ws

      ws.onopen = () => {
        setIsConnected(true)
        retriesRef.current = 0
      }

      ws.onmessage = (e) => {
        try {
          const payload = JSON.parse(e.data)
          setMessages((prev) => [...prev, payload])
          if (payload.status && TERMINAL.has(payload.status)) {
            setStatus(payload.status)
            ws.close()
          }
        } catch (_) {}
      }

      ws.onclose = () => {
        setIsConnected(false)
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
