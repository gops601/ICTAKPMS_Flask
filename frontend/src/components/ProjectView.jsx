import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertTriangle, History, Lock, RotateCcw, Trash2 } from 'lucide-react'
import { projectService, psService } from '../services/adminService'
import { errorMessage } from '../services/api'
import { useAuth } from '../context/AuthContext'
import Modal from './Modal'
import Alert from './Alert'
import Spinner from './Spinner'
import StatusBadge from './StatusBadge'
import { ProgressBar, StageBadge } from './ProjectBadges'
import GithubPanel from './GithubPanel'
import FeedbackPanel from './FeedbackPanel'
import ConfirmDialog from './ConfirmDialog'
import ProjectMentorsModal from './ProjectMentorsModal'
import ProjectTeamModal from './ProjectTeamModal'

const STAGE_LABEL = {
  allocated: 'Project Allocated', srs_preparation: 'SRS Preparation', srs_submitted: 'SRS Submitted',
  srs_under_review: 'SRS Under Review', srs_changes_requested: 'SRS Changes Requested', srs_approved: 'SRS Approved',
  implementation: 'Implementation', final_evaluation: 'Final Evaluation', completed: 'Completed',
}
const REOPEN_TARGETS = ['srs_preparation', 'implementation', 'final_evaluation']
const ACTION_HELP = {
  srs_preparation: 'Start preparing the SRS document.',
  implementation: 'Begin implementation (SRS is approved).',
  final_evaluation: 'Move to the final evaluation.',
  completed: 'Mark the project as completed.',
}
const fmtDate = (d) => (d ? new Date(`${d}T00:00:00`).toLocaleDateString() : '—')
const fmtTime = (iso) => new Date(`${iso}Z`).toLocaleString()

function describe(item) {
  if (item.kind === 'transition') {
    const to = STAGE_LABEL[item.to] || item.to
    if (item.is_reopen) return `Reopened: ${STAGE_LABEL[item.from]} → ${to}`
    return item.from ? `${STAGE_LABEL[item.from]} → ${to}` : `Project allocated (${to})`
  }
  const map = {
    'problem_statement.changed': 'Project changed',
    'mentor.changed': 'Mentor changed',
    'project.reopened': 'Project reopened',
    'project.closed': 'Project closed by the domain lead',
    'feedback.sent': 'Mentor sent feedback',
  }
  return map[item.action] || item.action
}

/** Whole-project view used by every role; the API decides what each role may do. */
export default function ProjectView({ id }) {
  const { user } = useAuth()
  const navigate = useNavigate()
  const role = user.role
  const canManage = role === 'admin' || role === 'domain_lead'
  const canClose = role === 'domain_lead' || role === 'admin'
  const canEditTeam = role === 'admin' || role === 'domain_lead' || role === 'mentor'   // never students; the server checks the mentor is on this project
  const [project, setProject] = useState(null)
  const [timeline, setTimeline] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [modal, setModal] = useState(null) // 'reopen' | 'close' | 'mentor' | 'problem' | { transition }
  const [form, setForm] = useState({})
  const [options, setOptions] = useState([])
  const [modalError, setModalError] = useState('')

  const load = useCallback(async () => {
    try {
      const [p, t] = await Promise.all([projectService.get(id), projectService.timeline(id)])
      setProject(p); setTimeline(t)
    } catch (e) { setError(errorMessage(e)) }
  }, [id])
  useEffect(() => { load() }, [load])

  const act = async (fn, closeModal = true) => {
    setBusy(true); setModalError('')
    try { await fn(); if (closeModal) setModal(null); setError(''); await load() }
    catch (e) { const msg = errorMessage(e); modal ? setModalError(msg) : setError(msg) } finally { setBusy(false) }
  }

  const openMentor = () => setModal('mentor')
  const openProblem = async () => {
    setForm({ ps_id: '' }); setModalError(''); setModal('problem')
    try {
      const r = await psService.list({ domain_id: project.batch.domain?.id, status: 'active', per_page: 100 })
      setOptions(r.items.filter((p) => p.id !== project.problem_statement.id))
    } catch (e) { setModalError(errorMessage(e)) }
  }

  if (error && !project) return <Alert>{error}</Alert>
  if (!project) return <Spinner />
  const canChangePs = canManage && ['allocated', 'srs_preparation'].includes(project.stage)

  return (
    <div className="max-w-5xl space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">{project.title}</h1>
          <p className="text-sm text-slate-500">
            <span className="font-mono text-slate-700">{project.code}</span> · {project.problem_statement.ps_code} · Batch {project.batch.code}{project.batch.domain ? ` · ${project.batch.domain.name}` : ''}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {project.is_delayed && <StatusBadge tone="red">Delayed</StatusBadge>}
          {project.project_type_label && <StatusBadge tone="blue">{project.project_type_label}</StatusBadge>}
          <StageBadge stage={project.stage} label={project.stage_label} />
          {project.total_weeks && <StatusBadge tone="grey">{project.mode === 'offline' ? 'Offline' : 'Online'} · {project.total_weeks} weeks</StatusBadge>}
          {project.is_closed && <StatusBadge tone="grey"><span className="inline-flex items-center gap-1"><Lock className="h-3 w-3" />Closed</span></StatusBadge>}
          {role === 'admin' && <button className="btn-danger" onClick={() => { setModalError(''); setModal('delete') }}><Trash2 className="h-4 w-4" />Delete</button>}
          {canClose && project.stage === 'completed' && !project.is_closed && (
            <button className="btn-primary" onClick={() => { setModalError(''); setModal('close') }}><Lock className="h-4 w-4" />Close project</button>
          )}
          {canClose && project.stage !== 'allocated' && (
            <button className="btn-secondary" onClick={() => { setForm({ to: 'implementation', reason: '' }); setModalError(''); setModal('reopen') }}>
              <RotateCcw className="h-4 w-4" />Reopen
            </button>
          )}
        </div>
      </div>

      <Alert>{error}</Alert>
      {project.is_delayed && (
        <Alert type="warning"><span className="flex items-start gap-2"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{project.delay_reasons.join(' · ')}</span></Alert>
      )}

      {project.available_actions.length > 0 && (
        <div className="card space-y-3" aria-label="Next steps">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Next step</h2>
          {project.available_actions.map((a) => (
            <div key={a.to} className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-sm font-medium">{a.label}</div>
                <div className="text-xs text-slate-500">{a.enabled ? ACTION_HELP[a.to] : a.reason}</div>
              </div>
              <button className="btn-primary" disabled={!a.enabled || busy} onClick={() => act(() => projectService.transition(project.id, a.to), false)}>
                {busy ? 'Working…' : a.to === 'srs_preparation' ? 'Start SRS preparation' : a.to === 'implementation' ? 'Start implementation' : `Move to ${a.label}`}
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="card md:col-span-2">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Overview</h2>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
            <div><dt className="text-slate-500">Progress</dt><dd><ProgressBar value={project.progress} /></dd></div>
            <div><dt className="text-slate-500">Difficulty</dt><dd className="capitalize">{project.problem_statement.difficulty}</dd></div>
            <div><dt className="text-slate-500">Start date</dt><dd>{fmtDate(project.start_date)}</dd></div>
            <div><dt className="text-slate-500">Target completion</dt><dd>{fmtDate(project.target_end_date)}</dd></div>
            {project.implementation_started_at && <div><dt className="text-slate-500">Implementation started</dt><dd>{fmtTime(project.implementation_started_at)}</dd></div>}
            {project.github_url && <div><dt className="text-slate-500">GitHub</dt><dd><a className="text-brand underline" href={project.github_url} target="_blank" rel="noreferrer">{project.github_url}</a></dd></div>}
          </dl>
          <div className="mt-4"><Link className="text-sm text-brand hover:underline" to={`/project-shelf/${project.problem_statement.id}`}>View on Project Shelf →</Link></div>
        </div>
        <div className="card space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">People</h2>
          <div>
            <div className="text-xs text-slate-500">{project.members.length > 1 ? 'Team' : 'Student'}</div>
            <ul className="text-sm">{project.members.map((m) => <li key={m.student_id}>{m.name}{m.is_lead ? ' (lead)' : ''} <span className="text-slate-400">· {m.registration_no}</span>{m.role && <span className="ml-2 rounded-full bg-brand-light px-2 py-0.5 text-xs font-medium text-brand-dark">{m.role}</span>}</li>)}</ul>
            {role === 'student' && project.members.length > 1 && <p className="mt-1 text-xs text-slate-500">Only your mentor or Domain Lead can change the group.</p>}
          </div>
          <div>
            <div className="text-xs text-slate-500">Mentor{project.mentors.length > 1 ? 's' : ''}{project.mentor_override ? ' (project-specific)' : ''}</div>
            {project.mentors.length ? (
              <ul className="text-sm">
                {project.mentors.map((m) => (
                  <li key={m.id}>{m.name}
                  </li>
                ))}
              </ul>
            ) : <div className="text-sm"><span className="text-slate-400">None assigned</span></div>}
          </div>
          {canEditTeam && project.stage !== 'completed' && !project.is_closed && <div><button className="btn-secondary" onClick={() => setModal('team')}>Change team</button></div>}
          {canManage && (
            <div className="flex flex-wrap gap-2">
              <button className="btn-secondary" onClick={openMentor}>Assign mentors</button>
              {canChangePs && <button className="btn-secondary" onClick={openProblem}>Change project</button>}
            </div>
          )}
        </div>
      </div>

      <div className="card flex flex-wrap items-center justify-between gap-3" aria-label="SRS summary">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">SRS</h2>
          <div className="mt-1 flex items-center gap-2 text-sm">
            <StatusBadge tone={{ approved: 'green', submitted: 'blue', under_review: 'orange', changes_requested: 'red' }[project.srs_status] || 'grey'}>
              {{ not_submitted: 'Not Submitted', submitted: 'Submitted', under_review: 'Under Review', changes_requested: 'Changes Requested', approved: 'Approved' }[project.srs_status]}
            </StatusBadge>
            <span className="text-slate-500">{project.implementation_unlocked ? 'Implementation unlocked' : 'Implementation locked until SRS approval'}</span>
          </div>
        </div>
        <Link className="btn-secondary" to={`/srs/${project.id}`}>{role === 'student' ? 'Open SRS' : 'View SRS'}</Link>
      </div>

      <div className="card flex flex-wrap items-center justify-between gap-3" aria-label="Scrum summary">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Scrum board</h2>
          <p className="mt-1 text-sm text-slate-500">{project.implementation_unlocked ? 'Plan and track development tasks.' : 'Unlocks once the SRS is approved.'}</p>
        </div>
        <Link className="btn-secondary" to={`/scrum/${project.id}`}>Open board</Link>
      </div>

      <div className="card flex flex-wrap items-center justify-between gap-3" aria-label="Reviews summary">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Weekly reviews & final evaluation</h2>
          <p className="mt-1 text-sm text-slate-500">Scores, feedback and the final sign-off required for completion.</p>
        </div>
        <Link className="btn-secondary" to={`/reviews/project/${project.id}`}>{role === 'mentor' || user?.is_mentor ? 'Evaluate' : 'View reviews'}</Link>
      </div>

      <GithubPanel projectId={project.id} />

      <div className="card">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Weekly review schedule</h2>
        <ul className={`grid grid-cols-2 gap-3 ${project.reviews.length === 3 ? 'sm:grid-cols-3' : 'sm:grid-cols-4'}`}>
          {project.reviews.map((r) => (
            <li key={r.week_no} className="rounded-lg border border-slate-200 p-3 text-sm">
              <div className="font-medium">Week {r.week_no}</div>
              <div className="text-xs text-slate-500">{r.week_no === 1 ? 'SRS & datasets' : 'Implementation'}</div>
              <div className="text-xs text-slate-500">Due {fmtDate(r.due_date)}</div>
              <div className="mt-1"><StatusBadge status={r.status} /></div>
            </li>
          ))}
        </ul>
      </div>

      <FeedbackPanel project={project} canSend={role === 'mentor' || Boolean(user?.is_mentor)} />

      <div className="card">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-slate-500"><History className="h-4 w-4" />Activity timeline</h2>
        <ol className="space-y-3 border-l-2 border-slate-200 pl-4">
          {timeline.map((it, i) => (
            <li key={i} className="text-sm">
              <div className="font-medium text-slate-800">{describe(it)}</div>
              <div className="text-xs text-slate-500">{it.actor} · {fmtTime(it.at)}</div>
              {(it.reason || it.details?.reason) && <div className="text-xs text-slate-600">“{it.reason || it.details.reason}”</div>}
            </li>
          ))}
        </ol>
      </div>

      {modal === 'delete' && (
        <ConfirmDialog danger confirmLabel="Delete permanently" busy={busy}
          message={`Permanently delete ${project.code || project.title}? Its reviews, Scrum board, SRS files and feedback are removed and cannot be recovered.`}
          onConfirm={async () => { setBusy(true); try { await projectService.remove(project.id); navigate('/admin/projects', { replace: true }) } catch (e) { setError(errorMessage(e)); setModal(null) } finally { setBusy(false) } }}
          onCancel={() => setModal(null)} />
      )}
      {modal === 'close' && (
        <ConfirmDialog confirmLabel="Close project" busy={busy}
          message="Close this completed project? Everyone involved is notified. You can reopen it later if needed."
          onConfirm={() => act(() => projectService.close(project.id))} onCancel={() => setModal(null)} />
      )}
      {modal === 'reopen' && (
        <Modal title="Reopen project" onClose={() => setModal(null)}
          footer={<><button className="btn-secondary" onClick={() => setModal(null)}>Cancel</button>
            <button className="btn-primary" disabled={busy} onClick={() => act(() => projectService.reopen(project.id, form.to, form.reason))}>{busy ? 'Reopening…' : 'Reopen project'}</button></>}>
          <div className="space-y-3">
            <Alert>{modalError}</Alert>
            <p className="text-sm text-slate-600">The project returns to an earlier stage. This is recorded in the audit log and everyone involved is notified.</p>
            <div><label htmlFor="reopen-to" className="label">Reopen to</label>
              <select id="reopen-to" className="input" value={form.to} onChange={(e) => setForm({ ...form, to: e.target.value })}>
                {REOPEN_TARGETS.map((s) => <option key={s} value={s}>{STAGE_LABEL[s]}</option>)}
              </select></div>
            <div><label htmlFor="reopen-reason" className="label">Reason (required)</label>
              <textarea id="reopen-reason" className="input" rows={3} value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} /></div>
          </div>
        </Modal>
      )}
      {modal === 'team' && <ProjectTeamModal project={project} onClose={() => setModal(null)} onSaved={() => { setModal(null); load() }} />}
      {modal === 'mentor' && <ProjectMentorsModal project={project} role={role} onClose={() => setModal(null)} onSaved={() => { setModal(null); load() }} />}
      {modal === 'problem' && (
        <Modal title="Change project" onClose={() => setModal(null)}
          footer={<><button className="btn-secondary" onClick={() => setModal(null)}>Cancel</button>
            <button className="btn-primary" disabled={busy || !form.ps_id} onClick={() => act(() => projectService.reassignProblem(project.id, Number(form.ps_id)))}>Change</button></>}>
          <div className="space-y-3">
            <Alert>{modalError}</Alert>
            <label htmlFor="pp" className="label">New project (from the Project Shelf)</label>
            <select id="pp" className="input" value={form.ps_id} onChange={(e) => setForm({ ps_id: e.target.value })}>
              <option value="">Select…</option>{options.map((p) => <option key={p.id} value={p.id}>{p.ps_code} – {p.title}</option>)}
            </select>
            <p className="text-xs text-slate-500">Possible until the SRS is submitted.</p>
          </div>
        </Modal>
      )}
    </div>
  )
}
