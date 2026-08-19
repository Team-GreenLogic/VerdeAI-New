import { useNavigate } from 'react-router-dom'
import ProfilePicker from '../components/ProfilePicker.jsx'

export default function DocumentsProfilePickerPage() {
  const navigate = useNavigate()

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Documents</h1>
        <p className="text-sm text-slate-500 mt-1">Select an org profile to upload and manage its compliance evidence documents.</p>
      </div>
      <ProfilePicker
        onSelect={pid => navigate(`/documents/${pid}`)}
        showCreateButton
        emptyHint="Create an org profile to start uploading documents."
      />
    </div>
  )
}
