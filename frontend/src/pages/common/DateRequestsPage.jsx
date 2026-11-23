import { useState } from 'react'
import { Link } from 'react-router-dom'
import { CalendarClock, Check, X } from 'lucide-react'
import { reviewDateService } from '../../services/adminService'
import { errorMessage } from '../../services/api'
import { useList } from '../../hooks/useList'
import { useAuth } from '../../context/AuthContext'
import BatchFilter from '../../components/BatchFilter'
import PageHeader from '../../components/PageHeader'
import DataTable from '../../components/DataTable'
import Pagination from '../../components/Pagination'
import Modal from '../../components/Modal'
import Alert from '../../components/Alert'
import StatusBadge from '../../components/StatusBadge'

const TONE = { pending: 'orange', approved: 'green', rejected: 'red', cancelled: 'grey' }
const fmt = (iso) => (iso ? new Date(`${iso}T00:00:00`).toLocaleDateString() : '—')

/**
 * Domain Leads (and admins) approve or reject review-date changes; mentors follow and withdraw their own requests.
 */
export default function DateRequestsPage() {
  const { user } = useAuth()
  const decider = user.role === 'domain_lead' || user.role === 'admin'
  const [status, setStatus] = useState(decider ? 'pending' : '')
  const [batchId, setBatchId] = useState('')
  const [page, setPage] = useState(1)
  const [dialog, setDialog] = useState(null) // { req, decision }
  const [note, setNote] = useState('')
  const [dialogError, setDialogError] = useState('')
  const [actionError, setActionError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const { items, meta, loading, error, reload } = useList(reviewDateService.list, { page, status: status || undefined, batch_id: batchId || undefined })

  const open = (req, decision) => { setDialog({ req, decision }); setNote(''); setDialogError('') }
  const submitDecision = async () => {
    if (dialog.decision === 'reject' && note.trim().length < 3) return setDialogError('Please give a reason for rejecting.')
    setBusy(true); setDialogError('')
    try {
      await reviewDateService.decide(dialog.req.id, dialog.decision, note)
      setNotice(dialog.decision === 'approve' ? 'Date change approved. The mentor and student were notified.' : 'Date change rejected. The mentor was notified.')
      setDialog(null); reload()
    } catch (e) { setDialogError(errorMessage(e)) } finally { setBusy(false) }
  }
  const withdraw = async (req) => {
    setActionError(''); setNotice('')
    try { await reviewDateService.cancel(req.id); setNotice('Request withdrawn.'); reload() } catch (e) { setActionError(errorMessage(e)) }
  }

  return (
    <div>
      <PageHeader title={decider ? 'Review Date Approvals' : 'My Date Requests'}
        subtitle={decider ? 'Mentors need your approval to move a review date that was already scheduled.' : 'Requests to move a scheduled review date, waiting for your Domain Lead.'} />
      <div className="card">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <BatchFilter value={batchId} onChange={(v) => { setBatchId(v); setPage(1) }} />
          <select className="input !w-auto" aria-label="Filter by status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }}>
            <option value="">Any status</option><option value="pending">Pending</option><option value="approved">Approved</option>
            <option value="rejected">Rejected</option><option value="cancelled">Withdrawn</option>
          </select>
        </div>
        <Alert>{error || actionError}</Alert>
        {notice && <Alert type="success">{notice}</Alert>}
        <DataTable loading={loading} rows={items} empty={status === 'pending' ? 'No date changes are waiting for approval.' : 'No date-change requests.'} columns={[
          { key: 'project', header: 'Project', render: (r) => <div><Link className="font-medium text-brand hover:underline" to={`/reviews/${r.review_id}`}>{r.project.title}</Link><div className="text-xs text-slate-500">Batch {r.project.batch.code} · {r.project.students.join(', ')}</div></div> },
          { key: 'week', header: 'Review', render: (r) => `Week ${r.week_no}` },
          { key: 'dates', header: 'Date change', render: (r) => (
            <div className="whitespace-nowrap"><span className="text-slate-500">{fmt(r.old_date)}</span> <CalendarClock className="mx-1 inline h-3.5 w-3.5 text-slate-400" aria-hidden /> <span className="font-semibold">{fmt(r.new_date)}</span>
              {r.due_date && <div className="text-xs text-slate-500">Due {fmt(r.due_date)}</div>}</div>) },
          { key: 'reason', header: 'Reason', render: (r) => <div className="max-w-xs"><div>{r.reason}</div><div className="text-xs text-slate-500">by {r.requested_by}</div>{r.decision_note && <div className="text-xs text-slate-500">“{r.decision_note}” – {r.decided_by}</div>}</div> },
          { key: 'status', header: 'Status', render: (r) => <StatusBadge tone={TONE[r.status]}>{r.status === 'cancelled' ? 'withdrawn' : r.status}</StatusBadge> },
          { key: 'actions', header: '', render: (r) => r.status !== 'pending' ? null : decider ? (
            <div className="flex gap-2">
              <button className="btn-primary" onClick={() => open(r, 'approve')} aria-label={`Approve date change for ${r.project.title} week ${r.week_no}`}><Check className="h-4 w-4" />Approve</button>
              <button className="btn-secondary" onClick={() => open(r, 'reject')} aria-label={`Reject date change for ${r.project.title} week ${r.week_no}`}><X className="h-4 w-4" />Reject</button>
            </div>
          ) : <button className="btn-secondary" onClick={() => withdraw(r)}>Withdraw</button> },
        ]} />
        <Pagination meta={meta} onPage={setPage} />
      </div>

      {dialog && (
        <Modal title={dialog.decision === 'approve' ? 'Approve date change' : 'Reject date change'} onClose={() => setDialog(null)}
          footer={<><button className="btn-secondary" onClick={() => setDialog(null)}>Cancel</button>
            <button className={dialog.decision === 'approve' ? 'btn-primary' : 'btn bg-red-600 text-white hover:bg-red-700'} disabled={busy} onClick={submitDecision}>
              {busy ? 'Saving…' : dialog.decision === 'approve' ? 'Approve' : 'Reject'}</button></>}>
          <div className="space-y-3">
            <Alert>{dialogError}</Alert>
            <p className="text-sm text-slate-700">
              Week {dialog.req.week_no} of <b>{dialog.req.project.title}</b>: {fmt(dialog.req.old_date)} → <b>{fmt(dialog.req.new_date)}</b>
              <br /><span className="text-slate-500">Mentor&apos;s reason: {dialog.req.reason}</span>
            </p>
            <label htmlFor="decision-note" className="label">{dialog.decision === 'approve' ? 'Note (optional)' : 'Reason for rejecting (required)'}</label>
            <textarea id="decision-note" className="input" rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
        </Modal>
      )}
    </div>
  )
}
