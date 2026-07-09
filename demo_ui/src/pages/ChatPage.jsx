import { createContext, useContext, useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const InListContext = createContext(false)
import { createSession, streamChat } from '../api/chat.js'
import Spinner from '../components/Spinner.jsx'

const SendSVG = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
  </svg>
)
const PencilSVG = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
  </svg>
)
const ChatBubbleSVG = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-12 h-12" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
  </svg>
)
const DocSVG = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
  </svg>
)
const CloseSVG = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
  </svg>
)

function CitationPanel({ citation, onClose }) {
  if (!citation) return null
  return (
    <div className="absolute top-0 right-0 w-80 h-full bg-white border-l border-slate-200 shadow-2xl z-40 flex flex-col animate-slide-in-right">
      <div className="flex items-center justify-between p-4 border-b border-slate-100 bg-slate-50/50 backdrop-blur-sm">
        <h3 className="font-semibold text-slate-800 text-sm flex items-center gap-2">
          <DocSVG />
          Document Reference
        </h3>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-slate-600 hover:bg-slate-100 p-1.5 rounded-full transition-colors"
        >
          <CloseSVG />
        </button>
      </div>
      <div className="p-5 overflow-y-auto scrollbar-thin">
        <div className="mb-4">
          <p className="font-semibold text-brand-700 text-sm">{citation.filename}</p>
          <p className="text-xs text-slate-500 mt-1">Page {citation.page}</p>
        </div>
        <div className="bg-slate-50 border border-slate-100 rounded-xl p-4 text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">
          {citation.text || 'No excerpt available.'}
        </div>
      </div>
    </div>
  )
}

function Message({ role, content, citations, streaming, onCitationClick }) {
  const [showCitations, setShowCitations] = useState(false)

  return (
    <div className={`flex gap-3 animate-fade-in-up ${role === 'user' ? 'justify-end' : 'justify-start'}`}>
      {/* Assistant avatar */}
      {role === 'assistant' && (
        <div className="w-7 h-7 rounded-full bg-brand-600 flex items-center justify-center flex-shrink-0 mt-1">
          <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4 text-white" viewBox="0 0 24 24" fill="currentColor">
            <path d="M17 8C8 10 5.9 16.17 3.82 21.34L5.71 22l1-2.3A4.49 4.49 0 008 20C19 20 22 3 22 3c-1 2-8 2-5 8z" />
          </svg>
        </div>
      )}

      <div className={`max-w-[75%] ${role === 'user' ? 'order-2' : ''}`}>
        <div
          className={`rounded-2xl px-5 py-3.5 text-sm leading-relaxed whitespace-pre-wrap shadow-sm ${
            role === 'user'
              ? 'bg-brand-600 text-white rounded-tr-sm'
              : 'bg-white border border-slate-200 text-slate-800 rounded-tl-sm'
          }`}
        >
          {streaming && !content ? (
            <span className="flex items-center gap-1 h-4">
              <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: '300ms' }} />
            </span>
          ) : role === 'assistant' ? (
            <div className="text-sm leading-relaxed text-slate-800 space-y-1">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  p: ({ children }) => {
                    const inList = useContext(InListContext)
                    return inList ? <>{children}</> : <p className="my-1 leading-relaxed">{children}</p>
                  },
                  ul: ({ children }) => <ul className="list-disc list-outside pl-4 my-1 space-y-0">{children}</ul>,
                  ol: ({ children }) => <ol className="list-decimal list-outside pl-4 my-1 space-y-0">{children}</ol>,
                  li: ({ children }) => (
                    <InListContext.Provider value={true}>
                      <li className="leading-relaxed">{children}</li>
                    </InListContext.Provider>
                  ),
                  strong: ({ children }) => <strong className="font-semibold text-slate-900">{children}</strong>,
                  em: ({ children }) => <em className="italic">{children}</em>,
                  code: ({ inline, children }) => inline
                    ? <code className="bg-slate-100 text-slate-700 rounded px-1 py-0.5 text-xs font-mono">{children}</code>
                    : <code className="block bg-slate-100 text-slate-700 rounded-lg p-3 text-xs font-mono overflow-x-auto my-1">{children}</code>,
                  pre: ({ children }) => <pre className="my-1">{children}</pre>,
                  blockquote: ({ children }) => <blockquote className="border-l-2 border-brand-400 pl-3 text-slate-600 my-1">{children}</blockquote>,
                  h1: ({ children }) => <h1 className="font-semibold text-base text-slate-900 my-1">{children}</h1>,
                  h2: ({ children }) => <h2 className="font-semibold text-sm text-slate-900 my-1">{children}</h2>,
                  h3: ({ children }) => <h3 className="font-semibold text-sm text-slate-900 my-0.5">{children}</h3>,
                  a: ({ href, children }) => <a href={href} className="text-brand-600 hover:underline" target="_blank" rel="noopener noreferrer">{children}</a>,
                  table: ({ children }) => <table className="text-xs border-collapse my-1 w-full">{children}</table>,
                  th: ({ children }) => <th className="bg-slate-50 border border-slate-200 px-2 py-1 text-left font-semibold">{children}</th>,
                  td: ({ children }) => <td className="border border-slate-200 px-2 py-1">{children}</td>,
                }}
              >{content}</ReactMarkdown>
              {streaming && (
                <span className="inline-block w-0.5 h-4 bg-slate-400 ml-0.5 align-middle animate-pulse rounded" />
              )}
            </div>
          ) : (
            <>
              {content}
            </>
          )}
        </div>

        {/* Citations */}
        {citations?.length > 0 && (
          <div className="mt-1.5 pl-1">
            <button
              onClick={() => setShowCitations(v => !v)}
              className="inline-flex items-center gap-1 text-xs font-medium text-brand-600 hover:text-brand-700 transition-colors"
            >
              <DocSVG />
              {citations.length} source{citations.length > 1 ? 's' : ''}
              <svg xmlns="http://www.w3.org/2000/svg" className={`w-3 h-3 transition-transform ${showCitations ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {showCitations && (
              <div className="mt-1 space-y-1">
                {citations.map((c, i) => (
                  <button
                    key={i}
                    onClick={() => onCitationClick(c)}
                    className="w-full text-left text-xs text-brand-700 bg-brand-50 hover:bg-brand-100 border border-brand-100 rounded-lg px-3 py-1.5 transition-colors flex items-center gap-1.5"
                  >
                    <DocSVG />
                    {c.filename} — p.{c.page}
                  </button>
                ))}
              </div>
            )}
          </div>
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
  const [sessionId, setSessionId] = useState(() => {
    return sessionStorage.getItem('chat_session_id') || null
  })
  const [messages, setMessages] = useState(() => {
    try {
      const saved = sessionStorage.getItem('chat_messages')
      return saved ? JSON.parse(saved) : []
    } catch { return [] }
  })
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState('')
  const [activeCitation, setActiveCitation] = useState(null)
  const abortRef = useRef(null)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  // Persist messages to sessionStorage whenever they change
  useEffect(() => {
    // Only save non-streaming messages (skip mid-stream saves)
    const hasStreaming = messages.some(m => m.streaming)
    if (!hasStreaming && messages.length > 0) {
      sessionStorage.setItem('chat_messages', JSON.stringify(messages))
    }
  }, [messages])

  // Persist session ID
  useEffect(() => {
    if (sessionId) {
      sessionStorage.setItem('chat_session_id', sessionId)
    }
  }, [sessionId])

  useEffect(() => {
    if (!sessionId) {
      initSession()
    }
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
    sessionStorage.removeItem('chat_messages')
    sessionStorage.removeItem('chat_session_id')
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
    <div className="relative flex h-full overflow-hidden">
      <div className="flex flex-col h-full flex-1 max-w-4xl mx-auto px-4 w-full transition-all duration-300">
        {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Compliance Chat</h1>
          <p className="text-xs text-slate-400 mt-0.5">Ask anything about your ISO 14001 compliance</p>
        </div>
        <button
          onClick={newChat}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-800 border border-slate-200 rounded-lg px-3 py-1.5 hover:bg-slate-50 transition-colors"
        >
          <PencilSVG /> New Chat
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto py-5 scrollbar-thin flex flex-col">
        {messages.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center gap-5">
            <div className="text-slate-300">
              <ChatBubbleSVG />
            </div>
            <div>
              <p className="text-slate-700 font-semibold">Ask anything about your compliance</p>
              <p className="text-sm text-slate-400 mt-1">Answers are grounded in your uploaded documents</p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-xl">
              {SUGGESTIONS.map((s, i) => (
                <button
                  key={i}
                  onClick={() => sendMessage(s)}
                  disabled={!sessionId}
                  className="text-left text-xs text-slate-600 bg-white border border-slate-200 hover:border-brand-400 hover:bg-brand-50 rounded-xl px-4 py-3 shadow-sm hover:shadow-md transition-all disabled:opacity-50 flex items-start justify-between gap-2"
                >
                  <span>{s}</span>
                  <span className="text-slate-400 flex-shrink-0">→</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((m, i) => (
              <Message
                key={i}
                role={m.role}
                content={m.content}
                citations={m.citations}
                streaming={m.streaming}
                onCitationClick={setActiveCitation}
              />
            ))}

            {error && !streaming && (
              <div className="rounded-lg bg-red-50 border border-red-100 px-4 py-3 text-sm text-red-700">
                {error}
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-slate-200 pt-4">
        {!sessionId && !error && (
          <div className="flex items-center gap-2 mb-3 text-xs text-slate-400">
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
            className="flex-1 resize-none rounded-2xl border-2 border-slate-200 px-4 py-3 text-sm text-slate-900 shadow-sm focus:border-brand-500 focus:outline-none focus:ring-0 disabled:opacity-50 scrollbar-thin placeholder:text-slate-400 transition-colors"
            style={{ maxHeight: '120px', overflowY: 'auto' }}
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={streaming || !input.trim() || !sessionId}
            className="flex-shrink-0 rounded-2xl bg-brand-600 px-4 py-3 text-white hover:bg-brand-700 disabled:opacity-50 transition-colors flex items-center justify-center"
          >
            {streaming ? <Spinner size="sm" /> : <SendSVG />}
          </button>
        </div>
        <p className="text-xs text-slate-400 mt-3 text-center mb-2">
          Responses are grounded in your uploaded documents. Always verify important decisions.
        </p>
      </div>
      </div>
      
      <CitationPanel citation={activeCitation} onClose={() => setActiveCitation(null)} />
    </div>
  )
}
