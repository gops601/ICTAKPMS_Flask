import StatusBadge from './StatusBadge'

const STAGE_TONE = {
  allocated: 'grey', srs_preparation: 'blue', srs_submitted: 'blue', srs_under_review: 'orange',
  srs_changes_requested: 'red', srs_approved: 'green', implementation: 'blue', final_evaluation: 'orange', completed: 'green',
}

export function StageBadge({ stage, label }) {
  return <StatusBadge tone={STAGE_TONE[stage] || 'grey'}>{label || stage}</StatusBadge>
}

export function ProgressBar({ value }) {
  return (
    <div className="flex items-center gap-2" title={`${value}% complete`}>
      <div className="h-2 w-24 overflow-hidden rounded-full bg-slate-200">
        <div className="h-full rounded-full bg-brand" style={{ width: `${Math.min(100, value)}%` }} />
      </div>
      <span className="text-xs text-slate-600">{Math.round(value)}%</span>
    </div>
  )
}
