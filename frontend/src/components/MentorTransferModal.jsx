import { useEffect, useState } from 'react'
import { mentorService, userService } from '../services/adminService'
import { errorMessage } from '../services/api'
import Modal from './Modal'
import Alert from './Alert'

/**
 * Remove a mentor and (optionally) hand all their batches and projects to another mentor.
 * Admins act on everything; a domain lead's changes stay inside their own domains (the server enforces it).
 */
export default function MentorTransferModal({ mentor, onClose, onDone }) {
  const [pool, setPool] = useState([])
  const [pick, setPick] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  useEffect(() => {
    userService.mentors({ per_page: 100 })
      .then((r) => setPool(r.items.filter((m) => m.is_active && m.id !== mentor.id)))
      .catch((e) => setError(errorMessage(e)))
  }, [mentor.id])

  const run = async () => {
    setBusy(true); setError('')
    try { setResult(await mentorService.transfer(mentor.id, pick ? Number(pick) : null)) } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }

  if (result) {
    return (
      <Modal title={`${mentor.name} updated`} onClose={onDone}
        footer={<button className="btn-primary" onClick={onDone}>Done</button>}>
        <Alert type="success">{result.message}</Alert>
      </Modal>
    )
  }
  return (
    <Modal title={`Replace or remove ${mentor.name}`} onClose={onClose}
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" disabled={busy} onClick={run}>{busy ? 'Working…' : pick ? 'Reassign' : 'Remove mentor'}</button></>}>
      <div className="space-y-3">
        <Alert>{error}</Alert>
        <label htmlFor="mt-pick" className="label">Hand their batches and projects to</label>
        <select id="mt-pick" className="input" value={pick} onChange={(e) => setPick(e.target.value)}>
          <option value="">No one – just remove them</option>
          {pool.map((m) => <option key={m.id} value={m.id}>{m.name} ({m.project_count ?? 0} projects)</option>)}
        </select>
        <p className="text-xs text-slate-500">
          {mentor.name} leaves every batch you manage, and the projects they mentor there move to the chosen mentor (students and mentors are notified).
          Without a replacement, those projects fall back to the batch&apos;s remaining mentors. The account itself is not deleted.
        </p>
      </div>
    </Modal>
  )
}
