import { useState } from 'react'
import { CalendarClock } from 'lucide-react'
import { reviewDateService } from '../services/adminService'
import { errorMessage } from '../services/api'
import Alert from './Alert'
import Modal from './Modal'

/** Mentor's "Change date" button for a scheduled review. Shown only when `review.permissions.can_request_date_change`.
 *  The Domain Lead approves; students are told when the new date takes effect. */
export default function DateChangeButton({ review, onDone }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ new_date: '', reason: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  if (!review.permissions?.can_request_date_change) return null

  const send = async () => {
    setError('')
    if (!form.new_date) return setError('Choose the new date.')
    if (form.reason.trim().length < 5) return setError('Give a reason (at least 5 characters).')
    setBusy(true)
    try {
      await reviewDateService.create(review.id, form.new_date, form.reason)
      setOpen(false); setForm({ new_date: '', reason: '' }); onDone && onDone()
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }

  return (
    <>
      <button type="button" className="btn-secondary" onClick={() => { setError(''); setOpen(true) }}><CalendarClock className="h-4 w-4" />Change date</button>
      {open && (
        <Modal title={`Change Week ${review.week_no} review date`} onClose={() => setOpen(false)}
          footer={<><button className="btn-secondary" onClick={() => setOpen(false)}>Cancel</button><button className="btn-primary" disabled={busy} onClick={send}>{busy ? 'Sending…' : 'Send for approval'}</button></>}>
          <div className="space-y-3">
            <Alert>{error}</Alert>
            <p className="text-sm text-slate-600">Current date: <b>{review.review_date}</b>. Your Domain Lead approves the change; the students are notified as soon as it is approved.</p>
            <div><label htmlFor={`cd-date-${review.id}`} className="label">New review date</label>
              <input id={`cd-date-${review.id}`} type="date" className="input" min={new Date().toISOString().slice(0, 10)} value={form.new_date} onChange={(e) => setForm({ ...form, new_date: e.target.value })} /></div>
            <div><label htmlFor={`cd-reason-${review.id}`} className="label">Reason</label>
              <textarea id={`cd-reason-${review.id}`} className="input" rows={3} value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} /></div>
          </div>
        </Modal>
      )}
    </>
  )
}
