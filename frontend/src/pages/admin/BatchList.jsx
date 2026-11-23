import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Download, Eye, Pencil, Plus, Upload } from 'lucide-react'
import { batchService, domainService, ouService, reportService } from '../../services/adminService'
import { errorMessage } from '../../services/api'
import { useDebounced, useList } from '../../hooks/useList'
import PageHeader from '../../components/PageHeader'
import DataTable from '../../components/DataTable'
import Pagination from '../../components/Pagination'
import StatusBadge from '../../components/StatusBadge'
import ConfirmDialog from '../../components/ConfirmDialog'
import Alert from '../../components/Alert'

export default function BatchList() {
  const [q, setQ] = useState('')
  const [ouId, setOuId] = useState('')
  const [domainId, setDomainId] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState({ key: 'created', order: 'desc' })
  const [ous, setOus] = useState([])
  const [domains, setDomains] = useState([])
  const [toggle, setToggle] = useState(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const dq = useDebounced(q)

  useEffect(() => {
    ouService.list().then(setOus).catch(() => {})
    domainService.list().then(setDomains).catch(() => {})
  }, [])

  const { items, meta, loading, error, reload } = useList(batchService.list, {
    q: dq, ou_id: ouId || undefined, domain_id: domainId || undefined, status: status || undefined,
    page, sort: sort.key, order: sort.order,
  })

  const resetPage = (fn) => (e) => { fn(e.target.value); setPage(1) }
  const onSort = (key) => setSort((s) => ({ key, order: s.key === key && s.order === 'asc' ? 'desc' : 'asc' }))

  const confirmToggle = async () => {
    setBusy(true)
    try { await batchService.setStatus(toggle.id, toggle.status === 'active' ? 'closed' : 'active'); setToggle(null); reload() }
    catch (e) { setActionError(errorMessage(e)); setToggle(null) } finally { setBusy(false) }
  }

  return (
    <div>
      <PageHeader title="Batches" subtitle="All batches across OUs and domains."
        actions={<>
          <Link to="/admin/uploads?tab=batches" className="btn-secondary"><Upload className="h-4 w-4" />Bulk upload</Link>
          <Link to="/admin/batches/new" className="btn-primary"><Plus className="h-4 w-4" />New batch</Link>
        </>} />
      <div className="card">
        <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-4">
          <input className="input" placeholder="Search name or code…" aria-label="Search batches" value={q} onChange={resetPage(setQ)} />
          <select className="input" aria-label="Filter by OU" value={ouId} onChange={resetPage(setOuId)}>
            <option value="">All OUs</option>{ous.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
          <select className="input" aria-label="Filter by domain" value={domainId} onChange={resetPage(setDomainId)}>
            <option value="">All domains</option>{domains.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          <select className="input" aria-label="Filter by status" value={status} onChange={resetPage(setStatus)}>
            <option value="">Any status</option><option value="active">Active</option><option value="closed">Closed</option>
          </select>
        </div>
        <Alert>{error || actionError}</Alert>
        <DataTable loading={loading} rows={items} sort={sort} onSort={onSort} columns={[
          { key: 'code', header: 'Code', sortKey: 'code' },
          { key: 'name', header: 'Name', sortKey: 'name' },
          { key: 'ou', header: 'OU', render: (b) => b.ou.name },
          { key: 'domain', header: 'Domain', render: (b) => b.domain?.name || '—' },
          { key: 'start_date', header: 'Start', sortKey: 'start_date', render: (b) => b.start_date || '—' },
          { key: 'student_count', header: 'Students' },
          { key: 'status', header: 'Status', render: (b) => <StatusBadge status={b.status} /> },
          { key: 'actions', header: 'Actions', render: (b) => (
            <div className="flex gap-2">
              <Link className="btn-secondary" to={`/admin/batches/${b.id}/overview`}><Eye className="h-4 w-4" />View</Link>
              <Link className="btn-secondary" to={`/admin/batches/${b.id}`}><Pencil className="h-4 w-4" />Edit</Link>
              <button className="btn-secondary" aria-label={`Download detailed report for ${b.code}`} onClick={() => reportService.batchDetailed(b.id).catch((e) => setActionError(errorMessage(e, 'Download failed')))}><Download className="h-4 w-4" />Report</button>
              <button className="btn-secondary" onClick={() => setToggle(b)}>{b.status === 'active' ? 'Close' : 'Reopen'}</button>
            </div>
          ) },
        ]} />
        <Pagination meta={meta} onPage={setPage} />
      </div>
      {toggle && (
        <ConfirmDialog message={toggle.status === 'active' ? `Close batch ${toggle.code}?` : `Reopen batch ${toggle.code}?`}
          confirmLabel={toggle.status === 'active' ? 'Close batch' : 'Reopen'} danger={toggle.status === 'active'} busy={busy}
          onConfirm={confirmToggle} onCancel={() => setToggle(null)} />
      )}
    </div>
  )
}
