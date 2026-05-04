import React, { createContext, useContext, useState, useCallback } from 'react'
import { logout as apiLogout, isLoggedIn } from '../api/auth.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [loggedIn, setLoggedIn] = useState(isLoggedIn)

  const login = useCallback(() => setLoggedIn(true), [])

  const logout = useCallback(() => {
    apiLogout()
    setLoggedIn(false)
  }, [])

  return (
    <AuthContext.Provider value={{ loggedIn, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
