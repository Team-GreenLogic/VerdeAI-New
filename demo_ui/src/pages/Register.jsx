import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { register, login } from '../api/auth.js'
import { useAuth } from '../context/AuthContext.jsx'
import Spinner from '../components/Spinner.jsx'

export default function Register() {
  const [form, setForm] = useState({
    email: '', password: '', firstName: '', lastName: '', organisationName: '',
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login: authLogin } = useAuth()
  const navigate = useNavigate()

  function set(field) {
    return (e) => setForm(f => ({ ...f, [field]: e.target.value }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await register(form.email, form.password, form.firstName, form.lastName, form.organisationName)
      await login(form.email, form.password)
      authLogin()
      navigate('/dashboard')
    } catch (err) {
      setError(err.message || 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  const fields = [
    { key: 'firstName', label: 'First Name', type: 'text', placeholder: 'Jane' },
    { key: 'lastName', label: 'Last Name', type: 'text', placeholder: 'Doe' },
    { key: 'email', label: 'Email', type: 'email', placeholder: 'jane@company.com' },
    { key: 'password', label: 'Password', type: 'password', placeholder: '••••••••' },
    { key: 'organisationName', label: 'Organisation Name', type: 'text', placeholder: 'Acme Corp' },
  ]

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <span className="text-5xl">🌿</span>
          <h1 className="mt-3 text-2xl font-bold text-gray-900">VerdeAI</h1>
          <p className="mt-1 text-sm text-gray-500">Create your compliance workspace</p>
        </div>

        <div className="rounded-2xl bg-white p-8 shadow-sm border border-gray-100">
          <h2 className="mb-6 text-lg font-semibold text-gray-800">Create an account</h2>

          {error && (
            <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 border border-red-100">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {fields.map(({ key, label, type, placeholder }) => (
              <div key={key}>
                <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
                <input
                  type={type}
                  required
                  value={form[key]}
                  onChange={set(key)}
                  placeholder={placeholder}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
                />
              </div>
            ))}
            <button
              type="submit"
              disabled={loading}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60 transition-colors"
            >
              {loading && <Spinner size="sm" />}
              Create Account
            </button>
          </form>

          <p className="mt-5 text-center text-sm text-gray-500">
            Already have an account?{' '}
            <Link to="/login" className="font-medium text-brand-600 hover:text-brand-700">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
