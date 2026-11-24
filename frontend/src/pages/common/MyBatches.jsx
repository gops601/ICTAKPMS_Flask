import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Eye, UserPlus } from 'lucide-react'
import { batchService } from '../../services/adminService'
import { useDebounced, useList } from '../../hooks/useList'
import useBasePath from '../../hooks/useBasePath'
import PageHeader from '../../components/PageHeader'
import DataTable from '../../components/DataTable'
import Pagination from '../../components/Pagination'
import StatusBadge from '../../components/StatusBadge'
import Alert from '../../components/Alert'
import AddBatchMentorsModal from '../../components/AddBatchMentorsModal'
import { useAuth } from '../../context/AuthContext'

/** Read-only list of the batches the signed-in lead/mentor may access (scoping is done by the API). */
export default function MyBatches() {
  const base = useBasePath()
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const { user } = useAuth()
  const [adding, setAdding] = useState(null)
  const dq = useDebounced(q)
  const { items, meta, loading, error, reload } = useList(batchService.list, { q: dq, status: status || undefined, page })

  return (
    <div>
      <PageHeader title="My Batches" subtitle="Batches assigned to you." />
      <div className="card">
        <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <input className="input" placeholder="Search name or code…" aria-label="Search batches" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} />
          <select className="input" aria-label="Filter by status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }}>
            <option value="">Any status</option><option value="active">Active</option><option value="closed">Closed</option>
          </select>
        </div>
        <Alert>{error}</Alert>
        <DataTable loading={loading} rows={items} empty="No batches assigned yet." columns={[
          { key: 'code', header: 'Code' },
          { key: 'name', header: 'Name' },
          { key: 'ou', header: 'OU', render: (b) => b.ou.name },
          { key: 'domain', header: 'Domain', render: (b) => b.domain?.name || '—' },
          { key: 'student_count', header: 'Students' },
          { key: 'status', header: 'Status', render: (b) => <StatusBadge status={b.status} /> },
          { key: 'actions', header: '', render: (b) => (
            <div className="flex flex-wrap gap-2">
              <Link className="btn-secondary" to={`${base}/batches/${b.id}`}><Eye className="h-4 w-4" />View</Link>
              {user.role === 'domain_lead' && b.status === 'active' && <button className="btn-secondary" aria-label={`Add mentors to ${b.code}`} onClick={() => setAdding(b)}><UserPlus className="h-4 w-4" />Add mentors</button>}
            </div>) },
        ]} />
        <Pagination meta={meta} onPage={setPage} />
      </div>
      {adding && <AddBatchMentorsModal batch={adding} onClose={() => setAdding(null)} onDone={() => { setAdding(null); reload() }} />}
    </div>
  )
}
