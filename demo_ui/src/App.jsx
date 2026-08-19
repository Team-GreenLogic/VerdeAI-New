import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext.jsx'
import ProtectedRoute, { AdminRoute } from './components/ProtectedRoute.jsx'
import Layout from './components/Layout.jsx'

import Login from './pages/Login.jsx'
import Register from './pages/Register.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Documents from './pages/Documents.jsx'
import DocumentsProfilePickerPage from './pages/DocumentsProfilePickerPage.jsx'
import OrgProfilesListPage from './pages/OrgProfilesListPage.jsx'
import OrgProfileDetailPage from './pages/OrgProfileDetailPage.jsx'
import AnalysesProfilePickerPage from './pages/AnalysesProfilePickerPage.jsx'
import AnalysisListPage from './pages/AnalysisListPage.jsx'
import AnalysisDetailPage from './pages/AnalysisDetailPage.jsx'
import ChatPage from './pages/ChatPage.jsx'
import AdminVersionsPage from './pages/AdminVersionsPage.jsx'
import AdminVersionDetailPage from './pages/AdminVersionDetailPage.jsx'

import LandingPage from './pages/LandingPage.jsx'

function AppRoutes() {
  return (
    <Routes>
      {/* Public Landing Page */}
      <Route path="/" element={<LandingPage />} />

      {/* Public Auth */}
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      {/* Protected — wrapped in Layout */}
      <Route
        path="/dashboard"
        element={<ProtectedRoute><Layout><Dashboard /></Layout></ProtectedRoute>}
      />
      <Route
        path="/documents"
        element={<ProtectedRoute><Layout><DocumentsProfilePickerPage /></Layout></ProtectedRoute>}
      />
      <Route
        path="/documents/:profileId"
        element={<ProtectedRoute><Layout><Documents /></Layout></ProtectedRoute>}
      />
      <Route
        path="/org-profiles"
        element={<ProtectedRoute><Layout><OrgProfilesListPage /></Layout></ProtectedRoute>}
      />
      <Route
        path="/org-profiles/:profileId"
        element={<ProtectedRoute><Layout><OrgProfileDetailPage /></Layout></ProtectedRoute>}
      />
      <Route
        path="/analyses"
        element={<ProtectedRoute><Layout><AnalysesProfilePickerPage /></Layout></ProtectedRoute>}
      />
      <Route
        path="/analyses/:profileId"
        element={<ProtectedRoute><Layout><AnalysisListPage /></Layout></ProtectedRoute>}
      />
      <Route
        path="/analyses/:profileId/:analysisId"
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

