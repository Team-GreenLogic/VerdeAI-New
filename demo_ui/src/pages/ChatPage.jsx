import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { createSession, deleteSession, getChatContext, getSessionMessages, listSessions, streamChat } from '../api/chat.js'
import { listProfiles } from '../api/orgProfiles.js'
import Spinner from '../components/Spinner.jsx'
import MarkdownContent from '../components/MarkdownContent.jsx'

const LAST_PROFILE_KEY = 'verdeai_last_chat_profile_id'
const COLOMBO_DATE_TIME = new Intl.DateTimeFormat('en-LK', {
  timeZone: 'Asia/Colombo',
  year: 'numeric',
  month: 'short',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
})

function formatColomboDateTime(value) {
  if (!value) return 'Time unavailable'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Time unavailable' : COLOMBO_DATE_TIME.format(date)
}

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

function citationLabel(citation) {
  if (citation?.display_label) return citation.display_label
  if (citation?.type === 'analysis') return `Clause ${citation.clause_id} · ${citation.decision}`
  return `${citation?.filename || 'Document'} · p.${citation?.page ?? '?'}`
}

function CitationPanel({ citation, profileId, onClose }) {
  const closeRef = useRef(null)
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!citation) return
    closeRef.current?.focus()
    const closeOnEscape = (event) => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [citation, onClose])
  if (!citation) return null
  const isAnalysis = citation.type === 'analysis'
  const copyExcerpt = async () => {
    await navigator.clipboard?.writeText(citation.text || '')
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 p-4 backdrop-blur-[2px]"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="flex max-h-[85dvh] min-h-0 w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900"
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="citation-title"
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-900">
          <h3 id="citation-title" className="font-semibold text-slate-900 text-sm flex items-center gap-2">
            <DocSVG />
            {isAnalysis ? 'Gap Analysis Reference' : 'Document Reference'}
          </h3>
          <button
            ref={closeRef}
            onClick={onClose}
            aria-label="Close citation"
            className="text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800 dark:hover:text-slate-200 p-1.5 rounded-full transition-colors"
          >
            <CloseSVG />
          </button>
        </div>
        <div className="min-h-0 overflow-y-auto overscroll-contain p-5 scrollbar-thin">
          <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 dark:border-emerald-800 dark:bg-emerald-950/40">
            <p className="font-semibold text-emerald-900 text-sm dark:text-emerald-200">{citationLabel(citation)}</p>
            <p className="text-xs text-slate-500 mt-1 dark:text-slate-400">
              {isAnalysis
                ? `${citation.decision} · ${citation.version_id || 'ISO 14001'} · ${citation.analysis_id}`
                : `Page ${citation.page}${citation.clause_id ? ` · Clause ${citation.clause_id}` : ''}`}
            </p>
          </div>
          <div className="min-w-0 overflow-hidden rounded-xl border border-slate-100 bg-slate-50 p-4 text-sm leading-relaxed text-slate-700 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-200">
            <MarkdownContent className="break-words" content={citation.text || 'No excerpt available.'} />
          </div>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
            <button onClick={copyExcerpt} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700">
              {copied ? 'Copied' : 'Copy excerpt'}
            </button>
            {isAnalysis && citation.analysis_id && (
              <Link to={`/analyses/${profileId}/${citation.analysis_id}`} onClick={onClose} className="rounded-lg bg-brand-600 px-3 py-2 text-xs font-semibold text-white hover:bg-brand-700 dark:bg-emerald-700 dark:hover:bg-emerald-600">
                Open full analysis
              </Link>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function HistoryPanel({ open, collapsed, sessions, activeSessionId, onSelect, onDelete, onClose, onCollapse, onNew }) {
  const [query, setQuery] = useState('')
  const filtered = useMemo(() => sessions.filter(s => (s.title || 'New conversation').toLowerCase().includes(query.toLowerCase())), [sessions, query])
  return (
    <>
      {open && <button aria-label="Close history" onClick={onClose} className="fixed inset-0 z-30 bg-slate-950/30 lg:hidden" />}
      <aside className={`${open ? 'translate-x-0' : '-translate-x-full'} fixed inset-y-0 left-0 z-40 w-72 border-r border-slate-200 bg-white text-slate-900 shadow-xl transition-transform dark:border-slate-800 dark:bg-slate-950 dark:text-white dark:shadow-none lg:static lg:z-auto lg:translate-x-0 ${collapsed ? 'lg:w-[72px]' : 'lg:w-64'} flex flex-col flex-shrink-0`}>
      <div className="flex h-16 items-center justify-between border-b border-slate-200 px-4 dark:border-white/10">
        {!collapsed && <h3 className="font-semibold text-sm flex items-center gap-2 text-slate-800 dark:text-slate-100"><HistorySVG /> Conversations</h3>}
        <button onClick={onCollapse} title={collapsed ? 'Expand history' : 'Collapse history'} className="hidden lg:flex rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-white/10 dark:hover:text-white">
          <svg aria-hidden="true" className={`h-4 w-4 transition-transform ${collapsed ? '' : 'rotate-180'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="m9 18 6-6-6-6" /></svg>
        </button>
        <button onClick={onClose} className="lg:hidden rounded-lg p-2 text-slate-400 hover:bg-slate-100 dark:hover:bg-white/10"><CloseSVG /></button>
      </div>
      <div className="p-3">
        <button onClick={onNew} title="New conversation" className={`flex w-full items-center ${collapsed ? 'justify-center' : 'gap-2'} rounded-xl bg-emerald-500 px-3 py-2.5 text-sm font-semibold text-slate-950 hover:bg-emerald-400`}><PencilSVG />{!collapsed && 'New conversation'}</button>
        {!collapsed && <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search conversations" className="mt-3 w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-800 outline-none placeholder:text-slate-400 focus:border-emerald-500 dark:border-white/10 dark:bg-white/5 dark:text-white dark:placeholder:text-slate-500" />}
      </div>
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {filtered.length === 0 ? (
          !collapsed && <p className="text-xs text-slate-500 text-center p-6">No conversations found.</p>
        ) : (
          filtered.map((s) => (
            <button
              key={s.session_id}
              onClick={() => onSelect(s.session_id)}
              title={s.title || 'New conversation'}
              className={`w-full text-left px-3 py-3 hover:bg-slate-100 dark:hover:bg-white/10 transition-colors flex items-start justify-between gap-2 group ${
                s.session_id === activeSessionId ? 'bg-emerald-50 dark:bg-white/10 border-l-2 border-emerald-500 dark:border-emerald-400' : 'border-l-2 border-transparent'
              }`}
            >
              <div className="min-w-0 flex-1">
                <p className={`text-sm text-slate-700 dark:text-slate-200 truncate ${collapsed ? 'text-center' : ''}`}>{collapsed ? '•••' : (s.title || 'New conversation')}</p>
                {!collapsed && <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-0.5">
                  {formatColomboDateTime(s.last_message_at)} · {s.message_count} message{s.message_count === 1 ? '' : 's'}
                </p>}
              </div>
              {!collapsed && <span
                role="button"
                onClick={(e) => { e.stopPropagation(); onDelete(s.session_id) }}
                className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-red-400 p-1 flex-shrink-0 transition-all"
                title="Delete conversation"
              >
                <TrashSVG />
              </span>}
            </button>
          ))
        )}
      </div>
      </aside>
    </>
  )
}

function Message({ role, content, citations, streaming, onCitationClick }) {
  const [showCitations, setShowCitations] = useState(false)
  const [copied, setCopied] = useState(false)

  async function copyResponse() {
    await navigator.clipboard?.writeText(content || '')
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }

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

      <div className={`min-w-0 ${role === 'user' ? 'order-2 max-w-[82%]' : 'max-w-[calc(100%_-_2.5rem)] flex-1'}`}>
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
            <div className="min-w-0 max-w-full text-sm leading-relaxed text-slate-800 space-y-1 overflow-hidden">
              <MarkdownContent content={content} citations={citations} onCitationClick={onCitationClick} />
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

        {role === 'assistant' && content && !streaming && (
          <button onClick={copyResponse} className="mt-1.5 rounded-md px-2 py-1 text-[11px] font-medium text-slate-400 hover:bg-slate-100 hover:text-slate-700">
            {copied ? 'Copied response' : 'Copy response'}
          </button>
        )}

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
                    {c.type === 'analysis'
                      ? `Analysis · Clause ${c.clause_id} — ${c.decision}`
                      : `${c.filename} — p.${c.page}`}
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
  const [historyCollapsed, setHistoryCollapsed] = useState(false)
  const [chatContext, setChatContext] = useState(null)
  const abortRef = useRef(null)
  const inputRef = useRef(null)
  const messagesContainerRef = useRef(null)
  // Tracks whether the user is (still) scrolled near the bottom — a ref rather
  // than state so scrolling itself doesn't trigger a re-render/effect re-run.
  const stickToBottomRef = useRef(true)

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
    if (!inputRef.current) return
    inputRef.current.style.height = 'auto'
    inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 144)}px`
  }, [input])

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
    refreshChatContext()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profileId])

  // Only auto-follow the stream if the user hasn't scrolled away from the
  // bottom — otherwise every streamed token would yank their view back down.
  useLayoutEffect(() => {
    const pane = messagesContainerRef.current
    if (pane && stickToBottomRef.current) pane.scrollTop = pane.scrollHeight
  }, [messages])

  function handleMessagesScroll() {
    const el = messagesContainerRef.current
    if (!el) return
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    stickToBottomRef.current = distanceFromBottom < 80
  }

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
      const authoritative = await listSessions(profileId)
      setSessions(current => {
        const ids = new Set(authoritative.map(session => session.session_id))
        const pending = current.filter(session => session.optimistic && !ids.has(session.session_id))
        return [...pending, ...authoritative]
      })
    } catch (_) {
      // Non-fatal — history panel just stays empty
    }
  }

  async function refreshChatContext() {
    try {
      setChatContext(await getChatContext(profileId))
    } catch (_) {
      setChatContext(null)
    }
  }

  async function loadSession(id) {
    abortRef.current?.abort()
    stickToBottomRef.current = true
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
    if (!window.confirm('Delete this conversation? This cannot be undone.')) return
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
    stickToBottomRef.current = true
    setMessages([])
    setInput('')
    setStreaming(false)
    setError('')
    sessionStorage.removeItem('chat_messages')
    sessionStorage.removeItem('chat_session_id')
    initSession()
  }

  function stopStreaming() {
    abortRef.current?.abort()
    setStreaming(false)
    setMessages(current => current.map((message, index) => (
      index === current.length - 1 ? { ...message, streaming: false } : message
    )))
  }

  function sendMessage(question) {
    if (!question.trim() || streaming || !sessionId) return
    setError('')
    stickToBottomRef.current = true

    const existingSession = sessions.some(session => session.session_id === sessionId)
    if (!existingSession) {
      setSessions(current => [{
        session_id: sessionId,
        profile_id: profileId,
        title: question.trim(),
        last_message_at: new Date().toISOString(),
        message_count: 1,
        optimistic: true,
      }, ...current])
    }

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
        setSessions(current => current.map(session => session.session_id === sessionId
          ? { ...session, message_count: Math.max(session.message_count || 0, 2), last_message_at: new Date().toISOString() }
          : session))
        setStreaming(false)
        inputRef.current?.focus()
        refreshSessions()
        refreshChatContext()
      },
      (errMsg) => {
        setError(errMsg)
        if (!existingSession) setSessions(current => current.filter(session => session.session_id !== sessionId))
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
    <div className="relative flex h-full min-h-0 overflow-hidden bg-slate-50 dark:bg-slate-950">
      <HistoryPanel
        open={historyOpen}
        collapsed={historyCollapsed}
        sessions={sessions}
        activeSessionId={sessionId}
        onSelect={loadSession}
        onDelete={handleDeleteSession}
        onClose={() => setHistoryOpen(false)}
        onCollapse={() => setHistoryCollapsed(value => !value)}
        onNew={newChat}
      />
      <div className="flex min-h-0 min-w-0 flex-col h-full flex-1 w-full overflow-hidden">
        {/* Header */}
      <div className="flex min-h-16 items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <button onClick={() => setHistoryOpen(true)} className="rounded-lg border border-slate-200 p-2 text-slate-600 lg:hidden" aria-label="Open conversation history"><HistorySVG /></button>
          <div className="min-w-0">
          <h1 className="truncate text-base font-bold text-slate-900">Compliance intelligence</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Grounded in the latest gap analysis ·{' '}
            <button onClick={switchProfile} className="font-semibold text-brand-600 hover:text-brand-700 transition-colors">
              {activeProfile?.org_name || 'Untitled Profile'}
            </button>
          </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setHistoryOpen(v => !v)}
            className="hidden items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-slate-800 border border-slate-200 rounded-lg px-3 py-1.5 hover:bg-slate-50 transition-colors"
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

      {chatContext && (
        <div className={`mx-4 mt-3 rounded-xl border px-4 py-3 text-xs sm:mx-6 ${
          !chatContext.has_completed_analysis
            ? 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-700 dark:bg-amber-950/60 dark:text-amber-200'
            : chatContext.stale
              ? 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-700 dark:bg-amber-950/60 dark:text-amber-200'
              : 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-200'
        }`}>
          {chatContext.has_completed_analysis ? (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span>
                Using latest completed analysis · {chatContext.version_id} · {chatContext.gap_count} gap{chatContext.gap_count === 1 ? '' : 's'} ·{' '}
                {chatContext.created_at ? new Date(chatContext.created_at).toLocaleString() : 'date unavailable'}
              </span>
              <Link to={`/analyses/${profileId}/${chatContext.analysis_id}`} className="font-semibold underline underline-offset-2">
                View analysis
              </Link>
              {chatContext.stale && (
                <span className="basis-full">
                  Evidence changed after this analysis ({chatContext.new_chunk_count} new, {chatContext.removed_chunk_count} removed). Run delta re-analysis for current verdicts.
                </span>
              )}
              {chatContext.newer_analysis_status && (
                <span className="basis-full">A newer analysis is {chatContext.newer_analysis_status}; chat will switch when it completes.</span>
              )}
            </div>
          ) : (
            <div className="flex items-center justify-between gap-2">
              <span>No completed gap analysis exists. Chat can provide general ISO guidance but will not diagnose this organisation.</span>
              <Link to="/analyses" className="font-semibold underline underline-offset-2 whitespace-nowrap">Run analysis</Link>
            </div>
          )}
        </div>
      )}

      {/* Messages */}
      <div
        ref={messagesContainerRef}
        onScroll={handleMessagesScroll}
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-6 scrollbar-thin flex flex-col sm:px-6"
      >
        {messages.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center gap-5">
            <div className="text-slate-300">
              <ChatBubbleSVG />
            </div>
            <div>
              <p className="text-slate-700 font-semibold">Ask anything about your compliance</p>
              <p className="text-sm text-slate-400 mt-1">Answers use your latest completed gap analysis and its supporting evidence</p>
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
          <div className="mx-auto w-full max-w-4xl space-y-5">
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

          </div>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-slate-200 bg-white px-4 pb-3 pt-3 sm:px-6">
        <div className="mx-auto max-w-4xl">
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
            onClick={streaming ? stopStreaming : () => sendMessage(input)}
            disabled={!streaming && (!input.trim() || !sessionId)}
            aria-label={streaming ? 'Stop generating' : 'Send message'}
            className={`flex-shrink-0 rounded-2xl px-4 py-3 text-white disabled:opacity-50 transition-colors flex items-center justify-center ${streaming ? 'bg-slate-800 hover:bg-slate-900' : 'bg-brand-600 hover:bg-brand-700'}`}
          >
            {streaming ? <span className="h-3.5 w-3.5 rounded-sm bg-white" /> : <SendSVG />}
          </button>
        </div>
        <p className="text-xs text-slate-400 mt-3 text-center mb-2">
          Responses use your latest completed gap analysis. Always verify important decisions.
        </p>
        </div>
      </div>
      </div>
      
      <CitationPanel citation={activeCitation} profileId={profileId} onClose={() => setActiveCitation(null)} />
    </div>
  )
}
