import { useNavigate } from 'react-router-dom'
import ProfilePicker from '../components/ProfilePicker.jsx'

export default function RecommendationsProfilePickerPage() {
  const navigate = useNavigate()
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Personalized Recommendations</h1>
        <p className="mt-1 text-sm text-slate-500">
          Select a company profile to research relevant industry practices and personalize its latest gap-analysis recommendations.
        </p>
      </div>
      <ProfilePicker
        onSelect={profileId => navigate(`/recommendations/${profileId}`)}
        showCreateButton
        emptyHint="Create and complete a company profile before starting research."
      />
    </div>
  )
}
