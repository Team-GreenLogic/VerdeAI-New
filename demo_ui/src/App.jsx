import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext.jsx'
import ProtectedRoute, { AdminRoute } from './components/ProtectedRoute.jsx'
import Layout from './components/Layout.jsx'

import Login from './pages/Login.jsx'
import Register from './pages/Register.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Documents from './pages/Documents.jsx'
import OrgProfilePage from './pages/OrgProfilePage.jsx'
import AnalysisListPage from './pages/AnalysisListPage.jsx'
import AnalysisDetailPage from './pages/AnalysisDetailPage.jsx'
import ChatPage from './pages/ChatPage.jsx'
import AdminVersionsPage from './pages/AdminVersionsPage.jsx'
import AdminVersionDetailPage from './pages/AdminVersionDetailPage.jsx'

function AppRoutes() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      {/* Protected — wrapped in Layout */}
      <Route
        path="/dashboard"
        element={<ProtectedRoute><Layout><Dashboard /></Layout></ProtectedRoute>}
      />
      <Route
        path="/documents"
        element={<ProtectedRoute><Layout><Documents /></Layout></ProtectedRoute>}
      />
      <Route
        path="/org-profile"
        element={<ProtectedRoute><Layout><OrgProfilePage /></Layout></ProtectedRoute>}
      />
      <Route
        path="/analyses"
        element={<ProtectedRoute><Layout><AnalysisListPage /></Layout></ProtectedRoute>}
      />
      <Route
        path="/analyses/:id"
        element={<ProtectedRoute><Layout><AnalysisDetailPage /></Layout></ProtectedRoute>}
      />
      <Route
        path="/chat"
        element={<ProtectedRoute><Layout><ChatPage /></Layout></ProtectedRoute>}
      />

      {/* Admin-only */}
      <Route
        path="/admin/versions"
        element={<AdminRoute><Layout><AdminVersionsPage /></Layout></AdminRoute>}
      />
      <Route
        path="/admin/versions/:vid"
        element={<AdminRoute><Layout><AdminVersionDetailPage /></Layout></AdminRoute>}
      />

      {/* Default */}
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  )
}
