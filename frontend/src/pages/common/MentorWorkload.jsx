import { useState } from 'react'
import { userService } from '../../services/adminService'
import { useDebounced, useList } from '../../hooks/useList'
import PageHeader from '../../components/PageHeader'
import DataTable from '../../components/DataTable'
import Pagination from '../../components/Pagination'
import StatusBadge from '../../components/StatusBadge'
import Alert from '../../components/Alert'
import MentorTransferModal from '../../components/MentorTransferModal'
import { Repeat } from 'lucide-react'

/** Mentors visible to a Domain Lead (own domain + unassigned) with their current workload. */
export default function MentorWorkload() {
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [type, setType] = useState('')
  const dq = useDebounced(q)
  const [transfer, setTransfer] = useState(null)
  const { items, meta, loading, error, reload } = useList(userService.mentors, { q: dq, page, mentor_type: type || undefined })
  return (
    <div>
      <PageHeader title="Mentors" subtitle="Workload per mentor. Assign mentors to batches from the batch's Mentors tab, or replace / remove a mentor here." />
      <div className="card">
        <div className="mb-4 grid max-w-xl grid-cols-1 gap-3 sm:grid-cols-2">
          <input className="input" placeholder="Search name, email or company…" aria-label="Search mentors" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} />
          <select className="input" aria-label="Filter by mentor type" value={type} onChange={(e) => { setType(e.target.value); setPage(1) }}>
            <option value="">All mentors</option><option value="internal">Internal (ICT trainers)</option><option value="industry">External (industry)</option>
          </select>
        </div>
        <Alert>{error}</Alert>
        <DataTable loading={loading} rows={items} empty="No mentors found." columns={[
          { key: 'name', header: 'Name' }, { key: 'email', header: 'Email' },
          { key: 'type', header: 'Type', render: (m) => (m.mentor_type === 'industry'
            ? <div><StatusBadge tone="blue">Industry</StatusBadge><div className="mt-0.5 text-xs text-slate-500">{m.company}{m.industry_sector ? ` · ${m.industry_sector}` : ''}</div></div>
            : <StatusBadge tone="green">Internal</StatusBadge>) },
          { key: 'domain', header: 'Domain', render: (m) => m.domain?.name || <span className="text-slate-400">Any</span> },
          { key: 'batch_count', header: 'Batches' }, { key: 'project_count', header: 'Projects' },
          { key: 'status', header: 'Status', render: (m) => <StatusBadge status={m.is_active ? 'active' : 'inactive'} /> },
          { key: 'actions', header: '', render: (m) => (
            <button className="btn-secondary" aria-label={`Replace or remove ${m.name}`} onClick={() => setTransfer(m)}><Repeat className="h-4 w-4" />Replace / remove</button>) },
        ]} />
        <Pagination meta={meta} onPage={setPage} />
      </div>
      {transfer && <MentorTransferModal mentor={transfer} onClose={() => setTransfer(null)} onDone={() => { setTransfer(null); reload() }} />}
    </div>
  )
}
