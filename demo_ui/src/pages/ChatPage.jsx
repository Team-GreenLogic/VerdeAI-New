import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { createSession, deleteSession, getSessionMessages, listSessions, streamChat } from '../api/chat.js'
import { listProfiles } from '../api/orgProfiles.js'
import Spinner from '../components/Spinner.jsx'
import MarkdownContent from '../components/MarkdownContent.jsx'

const LAST_PROFILE_KEY = 'verdeai_last_chat_profile_id'

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
const HistorySVG = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
)
const TrashSVG = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
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
        <div className="bg-slate-50 border border-slate-100 rounded-xl p-4 text-sm text-slate-700 leading-relaxed">
          <MarkdownContent content={citation.text || 'No excerpt available.'} />
        </div>
      </div>
    </div>
  )
}

function HistoryPanel({ open, sessions, activeSessionId, onSelect, onDelete, onClose }) {
  if (!open) return null
  return (
    <div className="absolute top-0 left-0 w-80 h-full bg-white border-r border-slate-200 shadow-2xl z-40 flex flex-col animate-slide-in-left">
      <div className="flex items-center justify-between p-4 border-b border-slate-100 bg-slate-50/50 backdrop-blur-sm">
        <h3 className="font-semibold text-slate-800 text-sm flex items-center gap-2">
          <HistorySVG />
          Past Conversations
        </h3>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-slate-600 hover:bg-slate-100 p-1.5 rounded-full transition-colors"
        >
          <CloseSVG />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {sessions.length === 0 ? (
          <p className="text-sm text-slate-400 text-center p-6">No past conversations yet.</p>
        ) : (
          sessions.map((s) => (
            <button
              key={s.session_id}
              onClick={() => onSelect(s.session_id)}
              className={`w-full text-left px-4 py-3 border-b border-slate-50 hover:bg-slate-50 transition-colors flex items-start justify-between gap-2 group ${
                s.session_id === activeSessionId ? 'bg-brand-50' : ''
              }`}
            >
              <div className="min-w-0">
                <p className="text-sm text-slate-800 truncate">{s.title || 'New conversation'}</p>
                <p className="text-xs text-slate-400 mt-0.5">
                  {new Date(s.last_message_at).toLocaleString()} · {s.message_count} message{s.message_count === 1 ? '' : 's'}
                </p>
              </div>
              <span
                role="button"
                onClick={(e) => { e.stopPropagation(); onDelete(s.session_id) }}
                className="opacity-0 group-hover:opacity-100 text-slate-300 hover:text-red-500 p-1 flex-shrink-0 transition-all"
                title="Delete conversation"
              >
                <TrashSVG />
              </span>
            </button>
          ))
        )}
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
              <MarkdownContent content={content} />
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
  const [profiles, setProfiles] = useState([])
  const [profilesLoading, setProfilesLoading] = useState(true)
  const [profileId, setProfileId] = useState(() => {
    return sessionStorage.getItem('chat_profile_id') || null
  })
  const [pendingProfileId, setPendingProfileId] = useState('')
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
  const [sessions, setSessions] = useState([])
  const [historyOpen, setHistoryOpen] = useState(false)
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

  // Load the tenant's org profiles once on mount, and auto-select the last
  // used one (if it still exists) so returning users skip the picker.
  useEffect(() => {
    listProfiles().then(list => {
      setProfiles(list || [])
      if (!profileId) {
        const lastId = localStorage.getItem(LAST_PROFILE_KEY)
        const match = (list || []).find(p => p.profile_id === lastId)
        if (match) {
          sessionStorage.setItem('chat_profile_id', match.profile_id)
          setProfileId(match.profile_id)
        }
      }
    }).catch(() => setProfiles([])).finally(() => setProfilesLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Once a profile is selected, ensure a chat session exists for it and load
  // the profile's past conversations.
  useEffect(() => {
    if (!profileId) return
    if (!sessionId) {
      initSession()
    }
    refreshSessions()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profileId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  function selectProfile(pid) {
    if (!pid) return
    localStorage.setItem(LAST_PROFILE_KEY, pid)
    sessionStorage.setItem('chat_profile_id', pid)
    setProfileId(pid)
  }

  function switchProfile() {
    abortRef.current?.abort()
    setMessages([])
    setSessionId(null)
    setSessions([])
    setInput('')
    setStreaming(false)
    setError('')
    setPendingProfileId('')
    sessionStorage.removeItem('chat_messages')
    sessionStorage.removeItem('chat_session_id')
    sessionStorage.removeItem('chat_profile_id')
    setProfileId(null)
  }

  async function initSession() {
    try {
      const { session_id } = await createSession(profileId)
      setSessionId(session_id)
    } catch (_) {
      setError('Failed to create chat session. Is the Chat RAG service running?')
    }
  }

  async function refreshSessions() {
    try {
      setSessions(await listSessions(profileId))
    } catch (_) {
      // Non-fatal — history panel just stays empty
    }
  }

  async function loadSession(id) {
    abortRef.current?.abort()
    setStreaming(false)
    setError('')
    try {
      const history = await getSessionMessages(id)
      setMessages(history.map(m => ({ role: m.role, content: m.content, citations: m.citations })))
      setSessionId(id)
      sessionStorage.setItem('chat_session_id', id)
      sessionStorage.setItem('chat_messages', JSON.stringify(history))
      setHistoryOpen(false)
    } catch (_) {
      setError('Failed to load that conversation.')
    }
  }

  async function handleDeleteSession(id) {
    try {
      await deleteSession(id)
      setSessions(s => s.filter(x => x.session_id !== id))
      if (id === sessionId) {
        newChat()
      }
    } catch (_) {
      setError('Failed to delete that conversation.')
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
      profileId,
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
        refreshSessions()
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

  if (profilesLoading) {
    return <div className="flex justify-center items-center h-full"><Spinner size="lg" /></div>
  }

  if (profiles.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center gap-3 px-4">
        <div className="text-slate-300"><ChatBubbleSVG /></div>
        <p className="text-slate-700 font-semibold">No org profiles yet</p>
        <p className="text-sm text-slate-400 max-w-sm">Create an org profile to start chatting with your compliance documents.</p>
        <Link
          to="/org-profiles"
          className="inline-flex items-center gap-2 mt-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 transition-colors"
        >
          Create your first org profile
        </Link>
      </div>
    )
  }

  if (!profileId) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center gap-4 px-4">
        <div className="text-slate-300"><ChatBubbleSVG /></div>
        <div>
          <p className="text-slate-700 font-semibold">Choose an org profile to chat about</p>
          <p className="text-sm text-slate-400 mt-1">Answers will be grounded in that profile's documents and context</p>
        </div>
        <div className="flex items-center gap-2 w-full max-w-sm">
          <select
            value={pendingProfileId}
            onChange={e => setPendingProfileId(e.target.value)}
            className="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-brand-400"
          >
            <option value="" disabled>Select an org profile…</option>
            {profiles.map(p => (
              <option key={p.profile_id} value={p.profile_id}>{p.org_name || 'Untitled Profile'}</option>
            ))}
          </select>
          <button
            onClick={() => selectProfile(pendingProfileId)}
            disabled={!pendingProfileId}
            className="rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50 transition-colors"
          >
            Start Chat
          </button>
        </div>
      </div>
    )
  }

  const activeProfile = profiles.find(p => p.profile_id === profileId)

  return (
    <div className="relative flex h-full overflow-hidden">
      <div className="flex flex-col h-full flex-1 max-w-4xl mx-auto px-4 w-full transition-all duration-300">
        {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Compliance Chat</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Ask anything about your ISO 14001 compliance ·{' '}
            <button onClick={switchProfile} className="font-semibold text-brand-600 hover:text-brand-700 transition-colors">
              {activeProfile?.org_name || 'Untitled Profile'} (switch)
            </button>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setHistoryOpen(v => !v)}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-800 border border-slate-200 rounded-lg px-3 py-1.5 hover:bg-slate-50 transition-colors"
          >
            <HistorySVG /> History
          </button>
          <button
            onClick={newChat}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-800 border border-slate-200 rounded-lg px-3 py-1.5 hover:bg-slate-50 transition-colors"
          >
            <PencilSVG /> New Chat
          </button>
        </div>
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
      <HistoryPanel
        open={historyOpen}
        sessions={sessions}
        activeSessionId={sessionId}
        onSelect={loadSession}
        onDelete={handleDeleteSession}
        onClose={() => setHistoryOpen(false)}
      />
    </div>
  )
}
