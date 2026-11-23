import { useState } from 'react'
import { userService } from '../../services/adminService'
import { useDebounced, useList } from '../../hooks/useList'
import PageHeader from '../../components/PageHeader'
import DataTable from '../../components/DataTable'
import Pagination from '../../components/Pagination'
import StatusBadge from '../../components/StatusBadge'
import Alert from '../../components/Alert'

/** Mentors visible to a Domain Lead (own domain + unassigned) with their current workload. */
export default function MentorWorkload() {
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const dq = useDebounced(q)
  const { items, meta, loading, error } = useList(userService.mentors, { q: dq, page })
  return (
    <div>
      <PageHeader title="Mentors" subtitle="Workload per mentor. Assign mentors to batches from the batch's Mentors tab." />
      <div className="card">
        <div className="mb-4 max-w-sm"><input className="input" placeholder="Search name or email…" aria-label="Search mentors" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} /></div>
        <Alert>{error}</Alert>
        <DataTable loading={loading} rows={items} empty="No mentors found." columns={[
          { key: 'name', header: 'Name' }, { key: 'email', header: 'Email' },
          { key: 'domain', header: 'Domain', render: (m) => m.domain?.name || <span className="text-slate-400">Any</span> },
          { key: 'batch_count', header: 'Batches' }, { key: 'project_count', header: 'Projects' },
          { key: 'status', header: 'Status', render: (m) => <StatusBadge status={m.is_active ? 'active' : 'inactive'} /> },
        ]} />
        <Pagination meta={meta} onPage={setPage} />
      </div>
    </div>
  )
}
