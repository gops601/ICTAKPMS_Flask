import { useEffect, useState } from 'react'
import { batchMentorService, projectService, userService } from '../services/adminService'
import { errorMessage } from '../services/api'
import Modal from './Modal'
import Alert from './Alert'
import Spinner from './Spinner'

/**
 * Choose the mentor(s) of a project – one or several. A domain lead picks from the batch's mentors, an administrator
 * from any active mentor. Saving with nothing ticked falls back to the batch's mentors.
 * `project` needs id, batch {id, code} and mentors [{id}].
 */
export default function ProjectMentorsModal({ project, role, onClose, onSaved }) {
  const [options, setOptions] = useState(null)
  const [selected, setSelected] = useState(() => new Set(project.mentor_override ? project.mentors.map((m) => m.id) : []))
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let live = true
    const load = role === 'admin'
      ? userService.mentors({ per_page: 100 }).then((r) => r.items.filter((m) => m.is_active))
      : batchMentorService.list(project.batch.id)
    load.then((m) => live && setOptions(m)).catch((e) => live && setError(errorMessage(e)))
    return () => { live = false }
  }, [project.batch.id, role])

  const toggle = (id) => setSelected((cur) => { const n = new Set(cur); n.has(id) ? n.delete(id) : n.add(id); return n })
  const save = async () => {
    setBusy(true); setError('')
    try { await projectService.setMentors(project.id, [...selected], reason); onSaved() } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }

  return (
    <Modal title="Assign mentors" onClose={onClose}
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" disabled={busy || !options} onClick={save}>{busy ? 'Saving…' : 'Save'}</button></>}>
      <div className="space-y-3">
        <Alert>{error}</Alert>
        <p className="text-sm text-slate-600">Tick every mentor who should guide <b>{project.title}</b>. Leave all unticked to use the mentors of batch {project.batch.code}.</p>
        {!options ? <Spinner /> : options.length === 0 ? <p className="text-sm text-slate-500">No mentors available.</p> : (
          <ul className="max-h-64 space-y-2 overflow-y-auto" aria-label="Mentors">
            {options.map((m) => (
              <li key={m.id}><label className="flex items-center gap-3 text-sm"><input type="checkbox" checked={selected.has(m.id)} onChange={() => toggle(m.id)} />{m.name}</label></li>
            ))}
          </ul>
        )}
        <div><label htmlFor="pm-reason" className="label">Reason (optional)</label>
          <input id="pm-reason" className="input" maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} /></div>
        <p className="text-xs text-slate-500">
          {role === 'admin' ? 'You can choose any active mentor, even one outside this batch.' : `Only mentors assigned to batch ${project.batch.code} can be chosen.`}
          {' '}Mentors added or removed, and the students, are notified.
        </p>
      </div>
    </Modal>
  )
}
