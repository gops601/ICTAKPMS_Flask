import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { CalendarDays, Download, Plus, Repeat, Trash2, UserPlus } from 'lucide-react'
import { batchMentorService, batchService, projectService, reportService, studentService, userService } from '../../services/adminService'
import { errorMessage, fieldErrors } from '../../services/api'
import { useAuth } from '../../context/AuthContext'
import useBasePath from '../../hooks/useBasePath'
import PageHeader from '../../components/PageHeader'
import DataTable from '../../components/DataTable'
import Modal from '../../components/Modal'
import ConfirmDialog from '../../components/ConfirmDialog'
import Alert from '../../components/Alert'
import Spinner from '../../components/Spinner'
import StatusBadge from '../../components/StatusBadge'
import { ProgressBar, StageBadge } from '../../components/ProjectBadges'

const TABS = ['Students', 'Mentors', 'Projects']

function MentorsTab({ batch, canManage }) {
  const [mentors, setMentors] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [pool, setPool] = useState([])
  const [dialog, setDialog] = useState(null) // { type: 'assign'|'reassign'|'remove', mentor? }
  const [pick, setPick] = useState('')
  const [busy, setBusy] = useState(false)
  const [dialogError, setDialogError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try { setMentors(await batchMentorService.list(batch.id)) } catch (e) { setError(errorMessage(e)) } finally { setLoading(false) }
  }, [batch.id])
  useEffect(() => { load() }, [load])

  const open = async (type, mentor) => {
    setDialog({ type, mentor }); setPick(''); setDialogError('')
    if (type !== 'remove') {
      try { setPool((await userService.mentors({ per_page: 100 })).items.filter((m) => m.is_active)) } catch (e) { setDialogError(errorMessage(e)) }
    }
  }
  const run = async () => {
    setBusy(true); setDialogError('')
    try {
      if (dialog.type === 'assign') await batchMentorService.assign(batch.id, Number(pick))
      else if (dialog.type === 'reassign') await batchMentorService.reassign(batch.id, dialog.mentor.id, Number(pick))
      else await batchMentorService.remove(batch.id, dialog.mentor.id)
      setDialog(null); load()
    } catch (e) { setDialogError(errorMessage(e)) } finally { setBusy(false) }
  }
  const assignedIds = new Set(mentors.map((m) => m.id))
  const choices = pool.filter((m) => !assignedIds.has(m.id))

  return (
    <div className="space-y-3">
      <Alert>{error}</Alert>
      {canManage && <div><button className="btn-primary" onClick={() => open('assign')}><UserPlus className="h-4 w-4" />Assign mentor</button></div>}
      <DataTable loading={loading} rows={mentors} empty="No mentors assigned to this batch yet." columns={[
        { key: 'name', header: 'Name' }, { key: 'email', header: 'Email' },
        { key: 'designation', header: 'Designation', render: (m) => m.designation || '—' },
        ...(canManage ? [{ key: 'actions', header: '', render: (m) => (
          <div className="flex gap-2">
            <button className="btn-secondary" onClick={() => open('reassign', m)}><Repeat className="h-4 w-4" />Reassign</button>
            <button className="btn-secondary" onClick={() => open('remove', m)} aria-label={`Remove ${m.name}`}><Trash2 className="h-4 w-4" /></button>
          </div>
        ) }] : []),
      ]} />
      {dialog && dialog.type === 'remove' && (
        <ConfirmDialog danger confirmLabel="Remove" busy={busy} message={`Remove ${dialog.mentor.name} from this batch? Their access to the batch's projects ends.`}
          onConfirm={run} onCancel={() => setDialog(null)} />
      )}
      {dialog && dialog.type !== 'remove' && (
        <Modal title={dialog.type === 'assign' ? 'Assign mentor' : `Reassign ${dialog.mentor.name}`} onClose={() => setDialog(null)}
          footer={<><button className="btn-secondary" onClick={() => setDialog(null)}>Cancel</button>
            <button className="btn-primary" disabled={!pick || busy} onClick={run}>{busy ? 'Saving…' : dialog.type === 'assign' ? 'Assign' : 'Reassign'}</button></>}>
          <div className="space-y-3">
            <Alert>{dialogError}</Alert>
            <label htmlFor="mentor-pick" className="label">{dialog.type === 'assign' ? 'Mentor' : 'Replace with'}</label>
            <select id="mentor-pick" className="input" value={pick} onChange={(e) => setPick(e.target.value)}>
              <option value="">Select a mentor…</option>
              {choices.map((m) => <option key={m.id} value={m.id}>{m.name} ({m.project_count} projects)</option>)}
            </select>
            {dialog.type === 'reassign' && <p className="text-xs text-slate-500">Projects with a mentor override move to the new mentor too.</p>}
          </div>
        </Modal>
      )}
    </div>
  )
}

/** The domain lead (or admin) sets when projects in this batch start and end; allocation defaults to it. */
function ProjectDatesCard({ batch, canManage, onSaved }) {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({ start: batch.project_start_date || '', end: batch.project_end_date || '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [errs, setErrs] = useState({})
  const isSet = batch.project_start_date && batch.project_end_date

  const save = async (e) => {
    e.preventDefault(); setBusy(true); setError(''); setErrs({})
    try { onSaved(await batchService.setProjectDates(batch.id, form.start, form.end)); setEditing(false) }
    catch (err) { setError(errorMessage(err)); setErrs(fieldErrors(err)) } finally { setBusy(false) }
  }

  return (
    <div className="card">
      {!isSet && canManage && <div className="mb-3"><Alert type="warning">Project start and end dates have not been set for this batch yet. Please set them before allocating projects.</Alert></div>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3 text-sm">
          <CalendarDays className="h-5 w-5 text-slate-400" aria-hidden />
          <div><div className="text-slate-500">Project start</div><div className="font-medium">{batch.project_start_date || 'Not set'}</div></div>
          <div className="ml-6"><div className="text-slate-500">Project end</div><div className="font-medium">{batch.project_end_date || 'Not set'}</div></div>
        </div>
        {canManage && <button className="btn-secondary" onClick={() => setEditing(true)}>{isSet ? 'Change dates' : 'Set project dates'}</button>}
      </div>
      {editing && (
        <Modal title="Project start and end dates" onClose={() => setEditing(false)}>
          <form onSubmit={save} className="space-y-3">
            <Alert>{error}</Alert>
            <div><label htmlFor="pd-start" className="label">Project start date *</label>
              <input id="pd-start" type="date" required className="input" value={form.start} onChange={(e) => setForm({ ...form, start: e.target.value })} />
              {errs.project_start_date && <p className="mt-1 text-xs text-red-600">{errs.project_start_date}</p>}</div>
            <div><label htmlFor="pd-end" className="label">Project end date *</label>
              <input id="pd-end" type="date" required className="input" value={form.end} onChange={(e) => setForm({ ...form, end: e.target.value })} />
              {errs.project_end_date && <p className="mt-1 text-xs text-red-600">{errs.project_end_date}</p>}</div>
            <div className="flex justify-end gap-2">
              <button type="button" className="btn-secondary" onClick={() => setEditing(false)}>Cancel</button>
              <button className="btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Save dates'}</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}

export default function BatchDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const base = useBasePath()
  const canManage = user.role === 'admin' || user.role === 'domain_lead'
  const [batch, setBatch] = useState(null)
  const [tab, setTab] = useState('Students')
  const [students, setStudents] = useState(null)
  const [projects, setProjects] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => { batchService.get(id).then(setBatch).catch((e) => setError(errorMessage(e))) }, [id])
  useEffect(() => {
    if (tab === 'Students') studentService.list({ batch_id: id, per_page: 100 }).then((r) => setStudents(r.items)).catch((e) => setError(errorMessage(e)))
    if (tab === 'Projects') projectService.list({ batch_id: id, per_page: 100 }).then((r) => setProjects(r.items)).catch((e) => setError(errorMessage(e)))
  }, [tab, id])

  if (error && !batch) return <Alert>{error}</Alert>
  if (!batch) return <Spinner />

  return (
    <div className="space-y-4">
      <PageHeader title={`${batch.code} – ${batch.name}`} subtitle={`${batch.ou.name} · ${batch.domain?.name || 'No domain'} · ${batch.student_count} students`}
        actions={<>
          <StatusBadge status={batch.status} />
          {canManage && <button className="btn-secondary" onClick={() => reportService.batchDetailed(batch.id).catch((e) => setError(errorMessage(e, 'Download failed')))}><Download className="h-4 w-4" />Detailed report</button>}
          {canManage && batch.status === 'active' && <Link to={`${base}/batches/${batch.id}/allocate`} className="btn-primary"><Plus className="h-4 w-4" />Allocate projects</Link>}
        </>} />
      <Alert>{error}</Alert>
      <ProjectDatesCard batch={batch} canManage={canManage} onSaved={(b) => setBatch((old) => ({ ...old, ...b }))} />
      {Object.keys(batch.details).length > 0 && (
        <div className="card"><dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          {Object.entries(batch.details).map(([k, v]) => <div key={k}><dt className="text-slate-500">{k.replace(/_/g, ' ')}</dt><dd className="font-medium">{v}</dd></div>)}
        </dl></div>
      )}
      <div role="tablist" className="flex gap-2">
        {TABS.map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
            className={`rounded-lg px-4 py-2 text-sm font-medium ${tab === t ? 'bg-brand text-white' : 'bg-white text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50'}`}>{t}</button>
        ))}
      </div>
      <div className="card">
        {tab === 'Students' && (students === null ? <Spinner /> : (
          <DataTable rows={students} empty="No students in this batch." columns={[
            { key: 'name', header: 'Name' }, { key: 'registration_no', header: 'Reg. no' }, { key: 'email', header: 'Email' },
            { key: 'project', header: 'Project', render: (s) => s.project
              ? <Link className="text-brand hover:underline" to={`/projects/${s.project.id}`}>{s.project.title}</Link> : <span className="text-slate-400">Not allocated</span> },
            { key: 'stage', header: 'Stage', render: (s) => s.project ? <StageBadge stage={s.project.stage} label={s.project.stage.replace(/_/g, ' ')} /> : null },
          ]} />
        ))}
        {tab === 'Mentors' && <MentorsTab batch={batch} canManage={canManage} />}
        {tab === 'Projects' && (projects === null ? <Spinner /> : (
          <DataTable rows={projects} empty="No projects allocated yet." columns={[
            { key: 'title', header: 'Project', render: (p) => <Link className="text-brand hover:underline" to={`/projects/${p.id}`}>{p.title}</Link> },
            { key: 'members', header: 'Student(s)', render: (p) => p.members.map((m) => m.name).join(', ') },
            { key: 'mentors', header: 'Mentor', render: (p) => p.mentors.map((m) => m.name).join(', ') || '—' },
            { key: 'stage', header: 'Stage', render: (p) => <StageBadge stage={p.stage} label={p.stage_label} /> },
            { key: 'progress', header: 'Progress', render: (p) => <ProgressBar value={p.progress} /> },
          ]} />
        ))}
      </div>
    </div>
  )
}
