import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: '🏠' },
  { to: '/documents', label: 'Documents', icon: '📄' },
  { to: '/org-profile', label: 'Org Profile', icon: '🏢' },
  { to: '/analyses', label: 'Analysis', icon: '🔍' },
  { to: '/chat', label: 'Chat', icon: '💬' },
]

export default function Sidebar() {
  const { logout } = useAuth()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <aside className="flex h-screen w-56 flex-col border-r border-gray-200 bg-white">
      {/* Brand */}
      <div className="flex items-center gap-2 px-5 py-5 border-b border-gray-100">
        <span className="text-2xl">🌿</span>
        <span className="text-lg font-bold text-brand-700">VerdeAI</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
        {NAV.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? 'border-l-4 border-brand-600 bg-brand-50 text-brand-700 pl-2'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
              }`
            }
          >
            <span>{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Logout */}
      <div className="border-t border-gray-100 p-3">
        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 hover:text-gray-900 transition-colors"
        >
          <span>🚪</span> Logout
        </button>
      </div>
    </aside>
  )
}
