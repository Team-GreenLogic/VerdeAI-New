import { useNavigate } from 'react-router-dom'
import ProfilePicker from '../components/ProfilePicker.jsx'

export default function AnalysesProfilePickerPage() {
  const navigate = useNavigate()

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Gap Analysis</h1>
        <p className="text-sm text-slate-500 mt-1">Select an org profile to run or review ISO 14001 compliance gap analyses.</p>
      </div>
      <ProfilePicker
        onSelect={pid => navigate(`/analyses/${pid}`)}
        showCreateButton
        emptyHint="Create an org profile to start running gap analyses."
      />
    </div>
  )
}
