import { createContext, useContext, useEffect, useMemo, useState } from 'react'

const STORAGE_KEY = 'verdeai-theme'
const ThemeContext = createContext(null)

function systemPrefersDark() {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
}

function applyTheme(theme) {
  const dark = theme === 'dark' || (theme === 'system' && systemPrefersDark())
  document.documentElement.classList.toggle('dark', dark)
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
  return dark ? 'dark' : 'light'
}

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() => localStorage.getItem(STORAGE_KEY) || 'system')
  const [resolvedTheme, setResolvedTheme] = useState(() => applyTheme(theme))

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, theme)
    setResolvedTheme(applyTheme(theme))
    if (theme !== 'system') return undefined

    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const sync = () => setResolvedTheme(applyTheme('system'))
    media.addEventListener?.('change', sync)
    return () => media.removeEventListener?.('change', sync)
  }, [theme])

  const value = useMemo(() => ({
    theme,
    resolvedTheme,
    setTheme: (next) => setThemeState(['light', 'dark', 'system'].includes(next) ? next : 'system'),
  }), [theme, resolvedTheme])

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  return useContext(ThemeContext)
}
