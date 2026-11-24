import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Eye, UserPlus } from 'lucide-react'
import { projectService } from '../../services/adminService'
import { useAuth } from '../../context/AuthContext'
import ProjectMentorsModal from '../../components/ProjectMentorsModal'
import { useDebounced, useList } from '../../hooks/useList'
import PageHeader from '../../components/PageHeader'
import DataTable from '../../components/DataTable'
import Pagination from '../../components/Pagination'
import Alert from '../../components/Alert'
import BatchFilter from '../../components/BatchFilter'
import StatusBadge from '../../components/StatusBadge'
import { ProgressBar, StageBadge } from '../../components/ProjectBadges'

const STAGES = [
  ['allocated', 'Project Allocated'], ['srs_preparation', 'SRS Preparation'], ['srs_submitted', 'SRS Submitted'],
  ['srs_under_review', 'SRS Under Review'], ['srs_changes_requested', 'SRS Changes Requested'], ['srs_approved', 'SRS Approved'],
  ['implementation', 'Implementation'], ['final_evaluation', 'Final Evaluation'], ['completed', 'Completed'],
]

/** Scoped by the API: admin = all, lead = domain, mentor = assigned. */
export default function ProjectList({ title = 'Projects', subtitle = 'Progress, stage and delays across projects.' }) {
  const [q, setQ] = useState('')
  const [stage, setStage] = useState('')
  const [delayed, setDelayed] = useState(false)
  const [type, setType] = useState('')
  const [batchId, setBatchId] = useState('')
  const [page, setPage] = useState(1)
  const { user } = useAuth()
  const [assigning, setAssigning] = useState(null)
  const canAssign = user.role === 'domain_lead' || user.role === 'admin'
  const dq = useDebounced(q)
  const { items, meta, loading, error, reload } = useList(projectService.list, {
    q: dq, stage: stage || undefined, batch_id: batchId || undefined, delayed: delayed ? 1 : undefined, project_type: type || undefined, page,
  })

  return (
    <div>
      <PageHeader title={title} subtitle={subtitle} />
      <div className="card">
        <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-5">
          <input className="input" placeholder="Search title, student or reg. no…" aria-label="Search projects" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} />
          <BatchFilter value={batchId} onChange={(v) => { setBatchId(v); setPage(1) }} className="!w-full" />
          <select className="input" aria-label="Filter by stage" value={stage} onChange={(e) => { setStage(e.target.value); setPage(1) }}>
            <option value="">Any stage</option>{STAGES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
          <select className="input" aria-label="Filter by project type" value={type} onChange={(e) => { setType(e.target.value); setPage(1) }}>
            <option value="">Any project type</option><option value="addon_course">Add-on Course</option>
            <option value="summer_internship">Summer Internship</option><option value="other">Other</option>
          </select>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={delayed} onChange={(e) => { setDelayed(e.target.checked); setPage(1) }} />Delayed only</label>
        </div>
        <Alert>{error}</Alert>
        <DataTable loading={loading} rows={items} empty="No projects found." columns={[
          { key: 'title', header: 'Project', render: (p) => <div><div className="font-medium">{p.title}</div><div className="text-xs text-slate-500"><span className="font-mono">{p.code}</span> · {p.problem_statement.ps_code} · {p.batch.code}{p.project_type_label ? ` · ${p.project_type_label}` : ''}</div></div> },
          { key: 'members', header: 'Student(s)', render: (p) => p.members.map((m) => m.name).join(', ') },
          { key: 'mentors', header: 'Mentor', render: (p) => p.mentors.length ? p.mentors.map((m) => m.name).join(', ') : <span className="text-slate-400">—</span> },
          { key: 'stage', header: 'Stage', render: (p) => <StageBadge stage={p.stage} label={p.stage_label} /> },
          { key: 'progress', header: 'Progress', render: (p) => <ProgressBar value={p.progress} /> },
          { key: 'delay', header: '', render: (p) => p.is_delayed ? <StatusBadge tone="red">Delayed</StatusBadge> : null },
          { key: 'actions', header: '', render: (p) => (
            <div className="flex flex-wrap gap-2">
              <Link className="btn-secondary" to={`/projects/${p.id}`}><Eye className="h-4 w-4" />Open</Link>
              {canAssign && p.stage !== 'completed' && <button className="btn-secondary" aria-label={`Assign mentors to ${p.title}`} onClick={() => setAssigning(p)}><UserPlus className="h-4 w-4" />Assign mentor</button>}
            </div>) },
        ]} />
        <Pagination meta={meta} onPage={setPage} />
      </div>
      {assigning && <ProjectMentorsModal project={assigning} role={user.role} onClose={() => setAssigning(null)} onSaved={() => { setAssigning(null); reload() }} />}
    </div>
  )
}
