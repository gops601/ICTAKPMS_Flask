import { useCallback, useEffect, useState } from 'react'
import DataCollectionTable from '../../components/DataCollectionTable'
import { Link, useParams } from 'react-router-dom'
import { Pencil } from 'lucide-react'
import { psService } from '../../services/adminService'
import { errorMessage } from '../../services/api'
import useBasePath from '../../hooks/useBasePath'
import PageHeader from '../../components/PageHeader'
import AttachmentPanel from '../../components/AttachmentPanel'
import StatusBadge from '../../components/StatusBadge'
import Alert from '../../components/Alert'
import Spinner from '../../components/Spinner'
import ShelfReviewButtons from '../../components/ShelfReviewButtons'

const SECTIONS = [
  ['description', 'Project description'], ['problem_definition', 'Problem definition'],
  ['objectives', 'Project objectives'], ['scope', 'Scope'], ['expected_outcomes', 'Expected outcomes'],
  ['functional_requirements', 'Functional requirements'], ['non_functional_requirements', 'Non-functional requirements'],
  ['suggested_technologies', 'Suggested technologies'], ['dataset_info', 'Dataset information'], ['required_skills', 'Required skills'],
]
const DIFF_TONE = { easy: 'green', medium: 'orange', hard: 'red' }

/** Read-only view. Students/mentors reuse this component in later phases (can_edit comes from the API). */
export default function ProblemStatementDetail() {
  const { id } = useParams()
  const base = useBasePath()
  const [ps, setPs] = useState(null)
  const [error, setError] = useState('')

  const load = useCallback(() => psService.get(id).then(setPs).catch((e) => setError(errorMessage(e))), [id])
  useEffect(() => { load() }, [load])

  if (error) return <Alert>{error}</Alert>
  if (!ps) return <Spinner />

  return (
    <div className="max-w-4xl space-y-4">
      <PageHeader title={ps.title} subtitle={`${ps.ps_code} · ${ps.domain.name}${ps.subdomain ? ` › ${ps.subdomain.name}` : ''}${ps.estimated_duration ? ` · ${ps.estimated_duration}` : ''}`}
        actions={<>
          {ps.proposed_by && <StatusBadge tone="green">Student project · {ps.proposed_by.name}</StatusBadge>}
          <StatusBadge tone={ps.source_type === 'industry' ? 'blue' : 'green'}>{ps.source_type === 'industry' ? `Industry · ${ps.industry}` : 'Internal'}</StatusBadge>
          <StatusBadge tone={DIFF_TONE[ps.difficulty]}>{ps.difficulty}</StatusBadge>
          <StatusBadge status={ps.status} />
          <ShelfReviewButtons ps={ps} onDone={load} />
          {ps.can_edit && <Link to={`${base}/project-shelf/${ps.id}/edit`} className="btn-secondary"><Pencil className="h-4 w-4" />Edit</Link>}
        </>} />
      {ps.approval_status === 'pending' && <Alert type="warning">Added by a student and waiting for a mentor's approval (mentors and the domain lead can approve it above). It cannot be allocated, and the student cannot start the SRS, until a mentor approves it.</Alert>}
      {ps.approval_status === 'rejected' && <Alert>A mentor rejected this student project.</Alert>}
      {ps.proposal?.is_group && (
        <section className="card" aria-label="Group members">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">Group project · {ps.proposal.members.length} students</h2>
          <ul className="divide-y divide-slate-100 text-sm">
            {ps.proposal.members.map((m) => (
              <li key={m.student_id} className="flex flex-wrap items-center gap-2 py-1.5">
                <span className="font-medium">{m.name}</span><span className="text-slate-500">{m.registration_no}</span>
                {m.role && <StatusBadge tone="blue">{m.role}</StatusBadge>}{m.is_submitter && <span className="text-xs text-slate-400">submitted</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
      {SECTIONS.filter(([k]) => ps[k]).map(([k, label]) => (
        <section key={k} className="card" aria-label={label}>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">{label}</h2>
          {/* HTML is sanitised server-side (bleach allow-list) before storage. */}
          <div className="rich-content text-sm text-slate-800" dangerouslySetInnerHTML={{ __html: ps[k] }} />
        </section>
      ))}
      <DataCollectionTable rows={ps.data_collection} />
      <AttachmentPanel psId={ps.id} kind="datasets" title="Datasets" canEdit={false} items={ps.datasets} onChanged={load} />
      <AttachmentPanel psId={ps.id} kind="documents" title="Reference documents" canEdit={false} items={ps.documents} onChanged={load} />
    </div>
  )
}
