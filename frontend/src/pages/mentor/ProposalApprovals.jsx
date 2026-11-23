import { useState } from 'react'
import { Check, Download, X } from 'lucide-react'
import { proposalService } from '../../services/adminService'
import { errorMessage } from '../../services/api'
import { useDebounced, useList } from '../../hooks/useList'
import PageHeader from '../../components/PageHeader'
import DataTable from '../../components/DataTable'
import Pagination from '../../components/Pagination'
import StatusBadge from '../../components/StatusBadge'
import Modal from '../../components/Modal'
import Alert from '../../components/Alert'

const TONE = { pending: 'orange', approved: 'green', rejected: 'red', withdrawn: 'grey' }

/** Mentor queue of student-proposed problem statements for the mentor's batches. */
export default function ProposalApprovals() {
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('pending')
  const [page, setPage] = useState(1)
  const [decision, setDecision] = useState(null) // { proposal, kind }
  const [remarks, setRemarks] = useState('')
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const dq = useDebounced(q)
  const { items, meta, loading, error, reload } = useList(proposalService.list, { q: dq, status: status || undefined, page })

  const open = (proposal, kind) => { setDecision({ proposal, kind }); setRemarks(''); setActionError('') }
  const submit = async () => {
    setBusy(true); setActionError('')
    try {
      await proposalService.review(decision.proposal.id, decision.kind, remarks || null)
      setDecision(null); reload()
    } catch (e) { setActionError(errorMessage(e)) } finally { setBusy(false) }
  }
  const download = async (p) => { try { await proposalService.download(p) } catch (e) { setActionError(errorMessage(e, 'Download failed')) } }

  return (
    <div>
      <PageHeader title="Project Proposal Approvals" subtitle="Detailed project proposals uploaded by students in your batches." />
      <div className="card">
        <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <input className="input" placeholder="Search title or student…" aria-label="Search proposals" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} />
          <select className="input" aria-label="Filter by status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }}>
            <option value="">Any status</option><option value="pending">Pending</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="withdrawn">Withdrawn</option>
          </select>
        </div>
        <Alert>{error || (!decision && actionError)}</Alert>
        <DataTable loading={loading} rows={items} empty="Nothing to review." columns={[
          { key: 'title', header: 'Proposal', render: (p) => <div><div className="font-medium">{p.title}</div>{p.summary && <div className="line-clamp-2 text-xs text-slate-500">{p.summary}</div>}</div> },
          { key: 'student', header: 'Student', render: (p) => <div>{p.student.name}<div className="text-xs text-slate-500">{p.student.registration_no} · {p.student.batch.code}</div></div> },
          { key: 'status', header: 'Status', render: (p) => <StatusBadge tone={TONE[p.status]}>{p.status}</StatusBadge> },
          { key: 'actions', header: 'Actions', render: (p) => (
            <div className="flex gap-2">
              <button className="btn-secondary" onClick={() => download(p)} aria-label={`Download ${p.file.name}`}><Download className="h-4 w-4" /></button>
              {p.status === 'pending' && <>
                <button className="btn-primary" onClick={() => open(p, 'approve')}><Check className="h-4 w-4" />Approve</button>
                <button className="btn-secondary" onClick={() => open(p, 'reject')}><X className="h-4 w-4" />Reject</button>
              </>}
            </div>
          ) },
        ]} />
        <Pagination meta={meta} onPage={setPage} />
      </div>
      {decision && (
        <Modal title={`${decision.kind === 'approve' ? 'Approve' : 'Reject'} “${decision.proposal.title}”`} onClose={() => setDecision(null)}>
          <Alert>{actionError}</Alert>
          <label htmlFor="pr-remarks" className="label">Remarks{decision.kind === 'reject' ? ' *' : ' (optional)'}</label>
          <textarea id="pr-remarks" className="input min-h-[90px]" value={remarks} onChange={(e) => setRemarks(e.target.value)} />
          <div className="mt-4 flex justify-end gap-2">
            <button className="btn-secondary" onClick={() => setDecision(null)}>Cancel</button>
            <button className="btn-primary" disabled={busy || (decision.kind === 'reject' && !remarks.trim())} onClick={submit}>{busy ? 'Saving…' : decision.kind === 'approve' ? 'Approve' : 'Reject'}</button>
          </div>
        </Modal>
      )}
    </div>
  )
}
