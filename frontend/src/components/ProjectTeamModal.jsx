import { useEffect, useState } from 'react'
import { projectService, studentService } from '../services/adminService'
import { errorMessage } from '../services/api'
import Modal from './Modal'
import Alert from './Alert'
import TeamPicker from './TeamPicker'

/**
 * Change a project's team and roles. Only mentors of the project, the domain lead and admins reach this:
 * students cannot change their own group.
 */
export default function ProjectTeamModal({ project, onClose, onSaved }) {
  const [candidates, setCandidates] = useState(null)
  const [members, setMembers] = useState(project.members.map((m) => ({ student_id: m.student_id, role: m.role || '', is_lead: m.is_lead })))
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    studentService.list({ batch_id: project.batch.id, per_page: 100 })
      .then((r) => setCandidates(r.items.filter((s) => s.is_active !== false && (!s.project || s.project.id === project.id))))
      .catch((e) => { setError(errorMessage(e)); setCandidates([]) })
  }, [project.batch.id, project.id])

  const save = async () => {
    if (members.length === 0) return setError('A project needs at least one student.')
    setBusy(true); setError('')
    try { await projectService.setMembers(project.id, members, reason); onSaved() } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }

  return (
    <Modal title="Change team" onClose={onClose} wide
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" disabled={busy || candidates === null} onClick={save}>{busy ? 'Saving…' : 'Save team'}</button></>}>
      <div className="space-y-3">
        <Alert>{error}</Alert>
        <p className="text-sm text-slate-600">Tick the students who work on this project and give each a role. Only students of {project.batch.code} without another project are listed.
          Students removed here lose their Scrum task assignments on this project.</p>
        {candidates === null ? <p className="text-sm text-slate-500">Loading students…</p>
          : <TeamPicker students={candidates} members={members} onChange={setMembers} leadable idPrefix="pt" />}
        <div>
          <label htmlFor="pt-reason" className="label">Reason (optional)</label>
          <input id="pt-reason" className="input" maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
      </div>
    </Modal>
  )
}
