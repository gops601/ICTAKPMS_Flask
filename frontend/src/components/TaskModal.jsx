import { useEffect, useState } from 'react'
import { scrumService } from '../services/adminService'
import { errorMessage, fieldErrors } from '../services/api'
import Modal from './Modal'
import Alert from './Alert'
import Spinner from './Spinner'
import ConfirmDialog from './ConfirmDialog'

export const PRIORITIES = ['low', 'medium', 'high', 'critical']
const COLUMNS = [['backlog', 'Backlog'], ['todo', 'To Do'], ['in_progress', 'In Progress'], ['in_review', 'In Review'], ['completed', 'Completed']]
const fmt = (iso) => new Date(`${iso}Z`).toLocaleString()
const PRE_WORK = ['backlog', 'todo']

/**
 * Create a task, or open an existing one (details / comments / history).
 * Which controls appear is driven entirely by the board permissions returned by the API.
 */
export default function TaskModal({ projectId, taskId, members, permissions, onClose, onChanged }) {
  const creating = !taskId
  const [task, setTask] = useState(null)
  const [tab, setTab] = useState('Details')
  const [form, setForm] = useState({ title: '', description: '', priority: 'medium', status: 'backlog', assigned_student_id: '', start_date: '', due_date: '' })
  const [comment, setComment] = useState('')
  const [error, setError] = useState('')
  const [errs, setErrs] = useState({})
  const [busy, setBusy] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const fill = (t) => {
    setTask(t)
    setForm({ title: t.title, description: t.description || '', priority: t.priority, status: t.status,
      assigned_student_id: t.assignee ? String(t.assignee.student_id) : '', start_date: t.start_date || '', due_date: t.due_date || '' })
  }
  useEffect(() => {
    if (!taskId) return
    scrumService.task(taskId).then(fill).catch((e) => setError(errorMessage(e)))
  }, [taskId])

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const editable = creating ? permissions.can_create : permissions.can_edit

  const save = async (e) => {
    e.preventDefault()
    setBusy(true); setError(''); setErrs({})
    const body = {
      title: form.title, description: form.description, priority: form.priority,
      assigned_student_id: form.assigned_student_id ? Number(form.assigned_student_id) : null,
      start_date: form.start_date || null, due_date: form.due_date || null,
    }
    try {
      if (creating) await scrumService.create(projectId, { ...body, status: form.status })
      else fill(await scrumService.update(taskId, { ...body, version: task.version }))
      onChanged()
      if (creating) onClose()
    } catch (err) { setError(errorMessage(err)); setErrs(fieldErrors(err)) } finally { setBusy(false) }
  }

  const remove = async () => {
    setBusy(true)
    try { await scrumService.remove(taskId); onChanged(); onClose() } catch (err) { setError(errorMessage(err)); setConfirmDelete(false) } finally { setBusy(false) }
  }

  const addComment = async (e) => {
    e.preventDefault()
    if (!comment.trim()) return setError('Write a comment first.')
    setBusy(true); setError('')
    try { fill(await scrumService.comment(taskId, comment)); setComment(''); onChanged() } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }

  if (!creating && !task) return <Modal title="Task" onClose={onClose}>{error ? <Alert>{error}</Alert> : <Spinner />}</Modal>
  const err = (k) => errs[k] && <p className="mt-1 text-xs text-red-600">{errs[k]}</p>

  return (
    <Modal title={creating ? 'New task' : `Task #${task.id}`} onClose={onClose} wide>
      {!creating && (
        <div role="tablist" className="mb-4 flex gap-2 border-b border-slate-200">
          {['Details', `Comments (${task.comment_count})`, 'History'].map((t) => {
            const key = t.split(' ')[0]
            return <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}
              className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${tab === key ? 'border-brand text-brand' : 'border-transparent text-slate-600'}`}>{t}</button>
          })}
        </div>
      )}
      <Alert>{error}</Alert>

      {(creating || tab === 'Details') && (
        <form onSubmit={save} className="space-y-3">
          {!editable && !creating && permissions.reason && <p className="text-xs text-slate-500">{permissions.reason}</p>}
          <fieldset disabled={!editable} className="space-y-3">
            <div><label htmlFor="t-title" className="label">Title *</label>
              <input id="t-title" className="input" required value={form.title} onChange={set('title')} />{err('title')}</div>
            <div><label htmlFor="t-desc" className="label">Description</label>
              <textarea id="t-desc" className="input" rows={3} value={form.description} onChange={set('description')} />{err('description')}</div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div><label htmlFor="t-pri" className="label">Priority</label>
                <select id="t-pri" className="input" value={form.priority} onChange={set('priority')}>
                  {PRIORITIES.map((p) => <option key={p} value={p}>{p[0].toUpperCase() + p.slice(1)}</option>)}</select>{err('priority')}</div>
              <div><label htmlFor="t-assignee" className="label">Assigned to</label>
                <select id="t-assignee" className="input" value={form.assigned_student_id} onChange={set('assigned_student_id')}>
                  <option value="">Unassigned</option>{members.map((m) => <option key={m.student_id} value={m.student_id}>{m.name}</option>)}</select>{err('assigned_student_id')}</div>
              {creating && (
                <div><label htmlFor="t-status" className="label">Column</label>
                  <select id="t-status" className="input" value={form.status} onChange={set('status')}>
                    {COLUMNS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></div>
              )}
              <div><label htmlFor="t-start" className="label">Start date</label>
                <input id="t-start" type="date" className="input" value={form.start_date} onChange={set('start_date')} />{err('start_date')}</div>
              <div><label htmlFor="t-due" className="label">Due date</label>
                <input id="t-due" type="date" className="input" value={form.due_date} onChange={set('due_date')} />{err('due_date')}</div>
            </div>
          </fieldset>
          {!creating && (
            <dl className="grid grid-cols-2 gap-2 text-xs text-slate-500">
              <div>Status: <span className="text-slate-800">{COLUMNS.find(([k]) => k === task.status)[1]}</span></div>
              <div>Created by: <span className="text-slate-800">{task.created_by?.name || '—'}</span></div>
              {task.completed_at && <div>Completed: <span className="text-slate-800">{fmt(task.completed_at)}</span></div>}
            </dl>
          )}
          <div className="flex justify-between">
            <div>{!creating && permissions.can_delete && PRE_WORK.includes(task.status) && (
              <button type="button" className="btn-secondary" onClick={() => setConfirmDelete(true)}>Delete task</button>)}</div>
            <div className="flex gap-2">
              <button type="button" className="btn-secondary" onClick={onClose}>Close</button>
              {editable && <button className="btn-primary" disabled={busy}>{busy ? 'Saving…' : creating ? 'Create task' : 'Save changes'}</button>}
            </div>
          </div>
        </form>
      )}

      {!creating && tab === 'Comments' && (
        <div className="space-y-3">
          <ul className="space-y-2">
            {task.comments.length === 0 && <li className="text-sm text-slate-500">No comments yet.</li>}
            {task.comments.map((c) => (
              <li key={c.id} className="rounded-lg bg-slate-50 p-2 text-sm">
                <div className="text-xs text-slate-500">{c.user} · {fmt(c.created_at)}</div>
                <div className="whitespace-pre-wrap">{c.body}</div>
              </li>
            ))}
          </ul>
          {permissions.can_comment ? (
            <form onSubmit={addComment} className="space-y-2">
              <label htmlFor="t-comment" className="label">Add a comment</label>
              <textarea id="t-comment" className="input" rows={2} value={comment} onChange={(e) => setComment(e.target.value)} />
              <button className="btn-primary" disabled={busy}>Post comment</button>
            </form>
          ) : <p className="text-xs text-slate-500">You can read comments but not add them.</p>}
        </div>
      )}

      {!creating && tab === 'History' && (
        <ul className="space-y-2 border-l-2 border-slate-200 pl-3 text-sm">
          {task.history.map((h) => (
            <li key={h.id}>
              <span className="font-medium capitalize">{h.action}</span>
              {h.field && <span> · {h.field.replace(/_/g, ' ')}{h.old || h.new ? `: ${h.old ?? '—'} → ${h.new ?? '—'}` : ''}</span>}
              <div className="text-xs text-slate-500">{h.user} · {fmt(h.at)}</div>
            </li>
          ))}
        </ul>
      )}

      {confirmDelete && <ConfirmDialog danger confirmLabel="Delete task" busy={busy} message={`Delete “${task.title}”? It has not been started, so it will be removed from the board.`} onConfirm={remove} onCancel={() => setConfirmDelete(false)} />}
    </Modal>
  )
}
