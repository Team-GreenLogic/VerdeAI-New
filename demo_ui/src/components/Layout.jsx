import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import Sidebar from './Sidebar.jsx'
import { useAuth } from '../context/AuthContext.jsx'
import { useTheme } from '../context/ThemeContext.jsx'

const PAGE_LABELS = {
  '/dashboard': 'Dashboard', '/documents': 'Documents', '/org-profiles': 'Org Profiles',
  '/analyses': 'Gap Analysis', '/chat': 'Compliance Chat',
}

function getPageLabel(pathname) {
  if (/^\/analyses\/[^/]+\/[^/]+/.test(pathname)) return 'Analysis Detail'
  if (/^\/analyses\/[^/]+/.test(pathname)) return 'Gap Analysis'
  if (/^\/documents\/[^/]+/.test(pathname)) return 'Documents'
  if (/^\/org-profiles\/[^/]+/.test(pathname)) return 'Org Profile'
  if (/^\/admin\/versions\/[^/]+/.test(pathname)) return 'ISO Version Detail'
  if (pathname === '/admin/versions') return 'ISO Versions'
  return PAGE_LABELS[pathname] || ''
}

const THEME_OPTIONS = [
  { value: 'light', label: 'Light', icon: '☀' },
  { value: 'dark', label: 'Dark', icon: '☾' },
  { value: 'system', label: 'System', icon: '◐' },
]

function useDismissable(open, onClose) {
  const ref = useRef(null)
  useEffect(() => {
    if (!open) return undefined
    const dismiss = (event) => {
      if (event.key === 'Escape' || (event.type === 'pointerdown' && !ref.current?.contains(event.target))) onClose()
    }
    document.addEventListener('pointerdown', dismiss)
    document.addEventListener('keydown', dismiss)
    return () => {
      document.removeEventListener('pointerdown', dismiss)
      document.removeEventListener('keydown', dismiss)
    }
  }, [open, onClose])
  return ref
}

function ThemeMenu({ open, onClose }) {
  const { theme, setTheme } = useTheme()
  const ref = useDismissable(open, onClose)
  if (!open) return null
  return (
    <div ref={ref} className="absolute right-12 top-12 z-50 w-44 rounded-xl border border-slate-200 bg-white p-1.5 shadow-xl dark:border-slate-700 dark:bg-slate-900" role="menu" aria-label="Choose appearance">
      {THEME_OPTIONS.map(option => (
        <button key={option.value} onClick={() => { setTheme(option.value); onClose() }} className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm ${theme === option.value ? 'bg-brand-50 text-brand-700 dark:bg-emerald-950 dark:text-emerald-300' : 'text-slate-600 hover:bg-slate-50 dark:text-slate-300 dark:hover:bg-slate-800'}`} role="menuitemradio" aria-checked={theme === option.value}>
          <span aria-hidden="true">{option.icon}</span><span>{option.label}</span>
          {theme === option.value && <span className="ml-auto text-brand-600">✓</span>}
        </button>
      ))}
    </div>
  )
}

function AccountMenu({ open, onClose }) {
  const { user, roles, logout } = useAuth()
  const navigate = useNavigate()
  const ref = useDismissable(open, onClose)
  if (!open) return null
  const email = user?.email || 'Signed-in user'
  const name = user?.display_name || email.split('@')[0]
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0]).join('').toUpperCase() || 'V'
  return (
    <div ref={ref} className="absolute right-0 top-12 z-50 w-72 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900" role="menu" aria-label="Account menu">
      <div className="border-b border-slate-100 p-4 dark:border-slate-800">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-brand-700 font-bold text-white">{initials}</div>
          <div className="min-w-0"><p className="truncate text-sm font-semibold text-slate-900 dark:text-white">{name}</p><p className="truncate text-xs text-slate-500 dark:text-slate-400">{email}</p></div>
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5">{(roles || []).filter(role => !['offline_access', 'uma_authorization', 'default-roles-verdeai'].includes(role)).map(role => <span key={role} className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-semibold capitalize text-slate-600 dark:bg-slate-800 dark:text-slate-300">{role.replaceAll('-', ' ')}</span>)}</div>
      </div>
      <button onClick={() => { onClose(); logout(); navigate('/login') }} className="flex w-full items-center gap-2 px-4 py-3 text-sm font-medium text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40" role="menuitem">
        <span aria-hidden="true">↪</span> Sign out
      </button>
    </div>
  )
}

export default function Layout({ children }) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [themeOpen, setThemeOpen] = useState(false)
  const [accountOpen, setAccountOpen] = useState(false)
  const mainRef = useRef(null)
  const location = useLocation()
  const { user } = useAuth()
  const { resolvedTheme } = useTheme()
  useEffect(() => { setSidebarOpen(false); setThemeOpen(false); setAccountOpen(false) }, [location.pathname])
  useLayoutEffect(() => {
    if (mainRef.current) mainRef.current.scrollTop = 0
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
  }, [location.pathname])

  const pageLabel = getPageLabel(location.pathname)
  const edgeToEdge = location.pathname === '/chat'
  const displayName = user?.display_name || user?.email?.split('@')[0] || 'My Workspace'
  const initials = displayName.split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0]).join('').toUpperCase() || 'V'

  return (
    <div className="flex h-dvh overflow-hidden bg-gray-50 dark:bg-slate-950">
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      {sidebarOpen && <button className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm md:hidden" onClick={() => setSidebarOpen(false)} aria-label="Close navigation" />}

      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <header className="relative z-30 flex h-16 flex-shrink-0 items-center justify-between border-b border-gray-200/60 bg-white/90 px-4 backdrop-blur-md dark:border-slate-800 dark:bg-slate-900/90 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <button onClick={() => setSidebarOpen(true)} className="inline-flex rounded-xl p-2 text-slate-500 hover:bg-gray-100 dark:hover:bg-slate-800 md:hidden" aria-label="Open navigation">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" d="M4 6h16M4 12h16M4 18h16" /></svg>
            </button>
            <div className="min-w-0"><p className="truncate text-sm font-semibold text-slate-800 dark:text-slate-100">{pageLabel}</p><p className="hidden text-xs text-slate-400 sm:block">ISO 14001 Compliance Platform</p></div>
          </div>

          <div className="relative flex items-center gap-2">
            <button onClick={() => { setThemeOpen(value => !value); setAccountOpen(false) }} className="flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 text-slate-500 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800" aria-label="Change appearance" aria-expanded={themeOpen}> {resolvedTheme === 'dark' ? '☾' : '☀'} </button>
            <ThemeMenu open={themeOpen} onClose={() => setThemeOpen(false)} />
            <button onClick={() => { setAccountOpen(value => !value); setThemeOpen(false) }} className="flex items-center gap-2 rounded-xl p-1 pr-2 hover:bg-slate-50 dark:hover:bg-slate-800" aria-label="Open account menu" aria-expanded={accountOpen}>
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-brand-700 text-sm font-bold text-white shadow-md shadow-brand-200/50 dark:shadow-none">{initials}</span>
              <span className="hidden max-w-32 truncate text-xs font-medium text-slate-700 dark:text-slate-200 sm:block">{displayName}</span>
              <svg aria-hidden="true" className={`h-3.5 w-3.5 text-slate-400 transition-transform ${accountOpen ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="m6 9 6 6 6-6" />
              </svg>
            </button>
            <AccountMenu open={accountOpen} onClose={() => setAccountOpen(false)} />
          </div>
        </header>

        <main ref={mainRef} className={`relative min-h-0 flex-1 ${edgeToEdge ? 'overflow-hidden p-0' : 'overflow-y-auto overflow-x-hidden p-4 sm:p-6 lg:p-8'}`}>
          <div className="bg-blob bg-blob-1" /><div className="bg-blob bg-blob-2" /><div className="bg-blob bg-blob-3" />
          <div className={`relative z-10 ${edgeToEdge ? 'h-full min-h-0' : 'min-h-full'}`}>{children}</div>
        </main>
      </div>
    </div>
  )
}
