import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

export default function ProtectedRoute({ children }) {
  const { loggedIn } = useAuth()
  return loggedIn ? children : <Navigate to="/login" replace />
}
