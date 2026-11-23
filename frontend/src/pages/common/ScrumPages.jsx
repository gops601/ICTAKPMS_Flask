import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Eye } from 'lucide-react'
import { scrumService } from '../../services/adminService'
import { useList } from '../../hooks/useList'
import MyProjectGate from '../../components/MyProjectGate'
import ScrumBoard from '../../components/ScrumBoard'
import PageHeader from '../../components/PageHeader'
import DataTable from '../../components/DataTable'
import Pagination from '../../components/Pagination'
import Alert from '../../components/Alert'
import BatchFilter from '../../components/BatchFilter'
import { StageBadge } from '../../components/ProjectBadges'

export function ScrumProjectPage() {
  const { projectId } = useParams()
  return (
    <div className="space-y-4">
      <PageHeader title="Scrum Board" actions={<Link to={`/projects/${projectId}`} className="btn-secondary">Project details</Link>} />
      <ScrumBoard key={projectId} projectId={projectId} />
    </div>
  )
}

export function StudentScrumPage() {
  return (
    <MyProjectGate title="Scrum Board">
      {(p) => (
        <div className="space-y-4">
          <PageHeader title="Scrum Board" subtitle={p.title} />
          <ScrumBoard projectId={p.id} />
        </div>
      )}
    </MyProjectGate>
  )
}

/** Monitoring list for mentors / leads / admins: task counts, completion and overdue work per project. */
export function ScrumOverviewPage() {
  const [page, setPage] = useState(1)
  const [overdue, setOverdue] = useState(false)
  const [batchId, setBatchId] = useState('')
  const { items, meta, loading, error } = useList(scrumService.overview, { page, batch_id: batchId || undefined, overdue: overdue ? 1 : undefined })
  return (
    <div>
      <PageHeader title="Scrum Monitoring" subtitle="Task progress and delayed work across the projects you oversee." />
      <div className="card">
        <div className="mb-4 flex flex-wrap items-center gap-4">
          <BatchFilter value={batchId} onChange={(v) => { setBatchId(v); setPage(1) }} />
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={overdue} onChange={(e) => { setOverdue(e.target.checked); setPage(1) }} />Only projects with overdue tasks</label>
        </div>
        <Alert>{error}</Alert>
        <DataTable loading={loading} rows={items} rowKey="project_id" empty="No boards to show." columns={[
          { key: 'title', header: 'Project', render: (p) => <div><div className="font-medium">{p.title}</div><div className="text-xs text-slate-500">Batch {p.batch.code} · {p.members.join(', ')}</div></div> },
          { key: 'stage', header: 'Stage', render: (p) => <StageBadge stage={p.stage} label={p.stage_label} /> },
          { key: 'tasks', header: 'Tasks', render: (p) => p.stats.total },
          { key: 'done', header: 'Completed', render: (p) => `${p.stats.completed} (${p.stats.completion_pct}%)` },
          { key: 'wip', header: 'In progress / review', render: (p) => `${p.stats.by_status.in_progress} / ${p.stats.by_status.in_review}` },
          { key: 'overdue', header: 'Overdue', render: (p) => <span className={p.stats.overdue ? 'font-semibold text-red-600' : ''}>{p.stats.overdue}</span> },
          { key: 'actions', header: '', render: (p) => <Link className="btn-secondary" to={`/scrum/${p.project_id}`}><Eye className="h-4 w-4" />Open board</Link> },
        ]} />
        <Pagination meta={meta} onPage={setPage} />
      </div>
    </div>
  )
}
