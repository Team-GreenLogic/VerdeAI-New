import { useEffect, useRef, useState } from 'react'
import { createSession, streamChat } from '../api/chat.js'
import Spinner from '../components/Spinner.jsx'

function Message({ role, content, citations, streaming }) {
  return (
    <div className={`flex ${role === 'user' ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[75%] ${role === 'user' ? 'order-2' : ''}`}>
        <div
          className={`rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
            role === 'user'
              ? 'bg-brand-600 text-white rounded-tr-sm'
              : 'bg-white border border-gray-100 shadow-sm text-gray-800 rounded-tl-sm'
          }`}
        >
          {content}
          {streaming && (
            <span className="inline-block w-1.5 h-4 bg-gray-400 ml-0.5 animate-pulse rounded" />
          )}
        </div>

        {/* Citations */}
        {citations?.length > 0 && (
          <details className="mt-1">
            <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600 pl-1">
              {citations.length} source{citations.length > 1 ? 's' : ''}
            </summary>
            <div className="mt-1 space-y-1 pl-1">
              {citations.map((c, i) => (
                <div key={i} className="text-xs text-gray-500 bg-gray-50 rounded px-2 py-1">
                  📄 {c.filename} — p.{c.page}
                </div>
              ))}
            </div>
          </details>
        )}
      </div>
    </div>
  )
}

const SUGGESTIONS = [
  'What are my biggest ISO 14001 compliance gaps?',
  'What documents do I need for clause 6.1?',
  'Summarise my environmental aspects and impacts.',
  'What training records are required under ISO 14001?',
]

export default function ChatPage() {
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState('')
  const abortRef = useRef(null)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    initSession()
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function initSession() {
    try {
      const { session_id } = await createSession()
      setSessionId(session_id)
    } catch (_) {
      setError('Failed to create chat session. Is the Chat RAG service running?')
    }
  }

  function newChat() {
    abortRef.current?.abort()
    setMessages([])
    setInput('')
    setStreaming(false)
    setError('')
    initSession()
  }

  function sendMessage(question) {
    if (!question.trim() || streaming || !sessionId) return
    setError('')

    const userMsg = { role: 'user', content: question }
    const assistantMsg = { role: 'assistant', content: '', citations: [], streaming: true }
    setMessages(m => [...m, userMsg, assistantMsg])
    setInput('')
    setStreaming(true)

    abortRef.current = streamChat(
      question,
      sessionId,
      (token) => {
        setMessages(m => {
          const copy = [...m]
          copy[copy.length - 1] = {
            ...copy[copy.length - 1],
            content: copy[copy.length - 1].content + token,
          }
          return copy
        })
      },
      (citations) => {
        setMessages(m => {
          const copy = [...m]
          copy[copy.length - 1] = { ...copy[copy.length - 1], citations }
          return copy
        })
      },
      () => {
        setMessages(m => {
          const copy = [...m]
          copy[copy.length - 1] = { ...copy[copy.length - 1], streaming: false }
          return copy
        })
        setStreaming(false)
        inputRef.current?.focus()
      },
      (errMsg) => {
        setError(errMsg)
        setMessages(m => {
          const copy = [...m]
          copy[copy.length - 1] = { ...copy[copy.length - 1], streaming: false, content: '⚠ ' + errMsg }
          return copy
        })
        setStreaming(false)
      },
    )
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
  }

  return (
    <div className="flex flex-col h-full max-w-3xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-gray-100">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Chat</h1>
          <p className="text-xs text-gray-400 mt-0.5">Ask anything about your ISO 14001 compliance</p>
        </div>
        <button
          onClick={newChat}
          className="text-sm text-gray-500 hover:text-gray-800 border border-gray-200 rounded-lg px-3 py-1.5 hover:bg-gray-50 transition-colors"
        >
          ✏ New Chat
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto py-5 space-y-4 scrollbar-thin">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center gap-4 pt-10">
            <span className="text-5xl">💬</span>
            <div>
              <p className="text-gray-600 font-medium">Ask anything about your compliance</p>
              <p className="text-sm text-gray-400 mt-1">Answers are grounded in your uploaded documents</p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2">
              {SUGGESTIONS.map((s, i) => (
                <button
                  key={i}
                  onClick={() => sendMessage(s)}
                  disabled={!sessionId}
                  className="text-left text-xs text-gray-600 border border-gray-200 rounded-xl px-4 py-3 hover:bg-gray-50 hover:border-brand-300 transition-colors disabled:opacity-50"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <Message
            key={i}
            role={m.role}
            content={m.content}
            citations={m.citations}
            streaming={m.streaming}
          />
        ))}

        {error && !streaming && (
          <div className="rounded-lg bg-red-50 border border-red-100 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-gray-100 pt-4">
        {!sessionId && !error && (
          <div className="flex items-center gap-2 mb-3 text-xs text-gray-400">
            <Spinner size="sm" /> Connecting to chat service…
          </div>
        )}
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            rows={1}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={streaming || !sessionId}
            placeholder="Ask about your ISO 14001 compliance… (Enter to send)"
            className="flex-1 resize-none rounded-xl border border-gray-200 px-4 py-3 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 disabled:opacity-50 scrollbar-thin"
            style={{ maxHeight: '120px', overflowY: 'auto' }}
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={streaming || !input.trim() || !sessionId}
            className="flex-shrink-0 rounded-xl bg-brand-600 px-4 py-3 text-white hover:bg-brand-700 disabled:opacity-50 transition-colors"
          >
            {streaming ? <Spinner size="sm" /> : '➤'}
          </button>
        </div>
        <p className="text-xs text-gray-400 mt-2 text-center">
          Responses are grounded in your uploaded documents. Always verify important decisions.
        </p>
      </div>
    </div>
  )
}
