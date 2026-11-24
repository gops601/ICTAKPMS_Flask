import { useState } from 'react'
import { Check, X } from 'lucide-react'
import { proposalService } from '../services/adminService'
import { errorMessage } from '../services/api'
import Modal from './Modal'
import Alert from './Alert'

/**
 * Approve / reject a student's project right from the Project Shelf (mentors of the batch, the domain lead, admins).
 * Renders nothing unless the shelf entry is a student project that is still pending.
 */
export default function ShelfReviewButtons({ ps, onDone }) {
  const [kind, setKind] = useState(null)       // 'approve' | 'reject'
  const [remarks, setRemarks] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  if (!ps.proposal || ps.proposal.status !== 'pending') return null

  const close = () => { setKind(null); setRemarks(''); setError('') }
  const submit = async () => {
    setBusy(true); setError('')
    try { await proposalService.reviewFromShelf(ps.id, kind, remarks.trim() || null); close(); onDone() } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  const group = ps.proposal.is_group

  return (
    <>
      <button className="btn-primary" aria-label={`Approve ${ps.ps_code}`} onClick={() => setKind('approve')}><Check className="h-4 w-4" />Approve</button>
      <button className="btn-secondary" aria-label={`Reject ${ps.ps_code}`} onClick={() => setKind('reject')}><X className="h-4 w-4" />Reject</button>
      {kind && (
        <Modal title={`${kind === 'approve' ? 'Approve' : 'Reject'} “${ps.title}”`} onClose={close}>
          <Alert>{error}</Alert>
          {kind === 'approve' && (
            <p className="mb-3 text-sm text-slate-600">Approving makes it allocatable on the Project Shelf and <b>starts the project</b>
              {group ? ` for the whole group (${ps.proposal.members.length} students)` : ' for the student'} in SRS Preparation.</p>
          )}
          <label htmlFor="sr-remarks" className="label">Remarks{kind === 'reject' ? ' *' : ' (optional)'}</label>
          <textarea id="sr-remarks" className="input min-h-[90px]" value={remarks} onChange={(e) => setRemarks(e.target.value)} />
          <div className="mt-4 flex justify-end gap-2">
            <button className="btn-secondary" onClick={close}>Cancel</button>
            <button className="btn-primary" disabled={busy || (kind === 'reject' && !remarks.trim())} onClick={submit}>{busy ? 'Saving…' : kind === 'approve' ? 'Approve' : 'Reject'}</button>
          </div>
        </Modal>
      )}
    </>
  )
}
