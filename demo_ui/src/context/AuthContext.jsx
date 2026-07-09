import React, { createContext, useContext, useState, useCallback, useEffect } from 'react'
import { logout as apiLogout, isLoggedIn, fetchMe } from '../api/auth.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [loggedIn, setLoggedIn] = useState(isLoggedIn)
  const [roles, setRoles] = useState([])

  // Fetch server-side roles (includes ADMIN_EMAILS injection)
  const refreshRoles = useCallback(async () => {
    if (!isLoggedIn()) { setRoles([]); return }
    try {
      const me = await fetchMe()
      setRoles(me.roles ?? [])
    } catch (_) {
      setRoles([])
    }
  }, [])

  // Load roles on mount if already logged in
  useEffect(() => { refreshRoles() }, [refreshRoles])

  const login = useCallback(async () => {
    setLoggedIn(true)
    await refreshRoles()
  }, [refreshRoles])

  const logout = useCallback(() => {
    apiLogout()
    setLoggedIn(false)
    setRoles([])
  }, [])

  const isAdmin = roles.includes('admin')

  return (
    <AuthContext.Provider value={{ loggedIn, login, logout, roles, isAdmin }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
