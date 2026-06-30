import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

export default function ProtectedRoute({ children }) {
  const { loggedIn } = useAuth()
  return loggedIn ? children : <Navigate to="/login" replace />
}

export function AdminRoute({ children }) {
  const { loggedIn, isAdmin } = useAuth()
  if (!loggedIn) return <Navigate to="/login" replace />
  if (!isAdmin) return <Navigate to="/dashboard" replace />
  return children
}
