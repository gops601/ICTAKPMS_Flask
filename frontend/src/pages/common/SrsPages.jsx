import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Eye } from 'lucide-react'
import { srsService } from '../../services/adminService'
import { useList } from '../../hooks/useList'
import { useAuth } from '../../context/AuthContext'
import MyProjectGate from '../../components/MyProjectGate'
import SrsPanel from '../../components/SrsPanel'
import GithubPanel from '../../components/GithubPanel'
import PageHeader from '../../components/PageHeader'
import DataTable from '../../components/DataTable'
import Pagination from '../../components/Pagination'
import Alert from '../../components/Alert'
import BatchFilter from '../../components/BatchFilter'
import StatusBadge from '../../components/StatusBadge'

/** /srs/:projectId – any role with access to the project (the API decides; the panel adapts). */
export function SrsProjectPage() {
  const { projectId } = useParams()
  return (
    <div className="max-w-4xl space-y-4">
      <PageHeader title="SRS" actions={<Link to={`/projects/${projectId}`} className="btn-secondary">Project details</Link>} />
      <SrsPanel key={projectId} projectId={projectId} />
    </div>
  )
}

export function StudentSrsPage() {
  return (
    <MyProjectGate title="SRS Submission">
      {(p) => (
        <div className="max-w-4xl space-y-4">
          <PageHeader title="SRS Submission" subtitle="Prepare, submit and track your Software Requirements Specification." />
          <SrsPanel projectId={p.id} />
        </div>
      )}
    </MyProjectGate>
  )
}

export function StudentGithubPage() {
  return (
    <MyProjectGate title="GitHub Repository">
      {(p) => (
        <div className="max-w-3xl space-y-4">
          <PageHeader title="GitHub Repository" subtitle="Link your project repository for your mentor and Domain Lead." />
          <GithubPanel projectId={p.id} />
        </div>
      )}
    </MyProjectGate>
  )
}

/** Projects whose latest SRS awaits a decision. Mentors review; leads/admins monitor. */
export function SrsQueuePage() {
  const { user } = useAuth()
  const [page, setPage] = useState(1)
  const [batchId, setBatchId] = useState('')
  const { items, meta, loading, error } = useList(srsService.queue, { page, batch_id: batchId || undefined })
  const reviewer = user.role === 'mentor' || user.role === 'admin'
  return (
    <div>
      <PageHeader title={reviewer ? 'SRS Review Queue' : 'SRS Approval Status'}
        subtitle="Submitted SRS documents waiting for a decision, oldest first." />
      <div className="card">
        <div className="mb-4"><BatchFilter value={batchId} onChange={(v) => { setBatchId(v); setPage(1) }} /></div>
        <Alert>{error}</Alert>
        <DataTable loading={loading} rows={items} empty="No SRS documents are waiting for review." columns={[
          { key: 'title', header: 'Project', render: (p) => <div><div className="font-medium">{p.title}</div><div className="text-xs text-slate-500">Batch {p.batch.code}</div></div> },
          { key: 'members', header: 'Student(s)', render: (p) => p.members.map((m) => m.name).join(', ') },
          { key: 'version', header: 'Version', render: (p) => `v${p.srs_version}` },
          { key: 'at', header: 'Submitted', render: (p) => (p.srs_submitted_at ? new Date(`${p.srs_submitted_at}Z`).toLocaleString() : '—') },
          { key: 'stage', header: 'Status', render: (p) => <StatusBadge tone={p.stage === 'srs_under_review' ? 'orange' : 'blue'}>{p.stage === 'srs_under_review' ? 'Under review' : 'Awaiting review'}</StatusBadge> },
          { key: 'actions', header: '', render: (p) => <Link className="btn-secondary" to={`/srs/${p.id}`}><Eye className="h-4 w-4" />{reviewer ? 'Review' : 'View'}</Link> },
        ]} />
        <Pagination meta={meta} onPage={setPage} />
      </div>
    </div>
  )
}
