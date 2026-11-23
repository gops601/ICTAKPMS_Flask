import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Eye, Pencil, Plus, Upload } from 'lucide-react'
import { domainService, psService } from '../../services/adminService'
import { errorMessage } from '../../services/api'
import { useDebounced, useList } from '../../hooks/useList'
import useBasePath from '../../hooks/useBasePath'
import PageHeader from '../../components/PageHeader'
import DataTable from '../../components/DataTable'
import Pagination from '../../components/Pagination'
import StatusBadge from '../../components/StatusBadge'
import ConfirmDialog from '../../components/ConfirmDialog'
import Alert from '../../components/Alert'

const DIFF_TONE = { easy: 'green', medium: 'orange', hard: 'red' }

export default function ProblemStatementList() {
  const base = useBasePath()
  const [q, setQ] = useState('')
  const [domainId, setDomainId] = useState('')
  const [difficulty, setDifficulty] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState({ key: 'created', order: 'desc' })
  const [domains, setDomains] = useState([])
  const [toggle, setToggle] = useState(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const dq = useDebounced(q)

  useEffect(() => { domainService.list().then(setDomains).catch(() => {}) }, [])
  const { items, meta, loading, error, reload } = useList(psService.list, {
    q: dq, domain_id: domainId || undefined, difficulty: difficulty || undefined, status: status || undefined,
    page, sort: sort.key, order: sort.order,
  })
  const reset = (fn) => (e) => { fn(e.target.value); setPage(1) }
  const onSort = (key) => setSort((s) => ({ key, order: s.key === key && s.order === 'asc' ? 'desc' : 'asc' }))

  const confirmToggle = async () => {
    setBusy(true)
    try { await psService.setStatus(toggle.id, toggle.status === 'active' ? 'inactive' : 'active'); setToggle(null); reload() }
    catch (e) { setActionError(errorMessage(e)); setToggle(null) } finally { setBusy(false) }
  }

  return (
    <div>
      <PageHeader title="Problem Statements" subtitle="The catalogue of project problem statements for your domain(s)."
        actions={<>
          <Link to={`${base}/problem-statements/upload`} className="btn-secondary"><Upload className="h-4 w-4" />Bulk upload</Link>
          <Link to={`${base}/problem-statements/new`} className="btn-primary"><Plus className="h-4 w-4" />New problem statement</Link>
        </>} />
      <div className="card">
        <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-4">
          <input className="input" placeholder="Search title or ID…" aria-label="Search problem statements" value={q} onChange={reset(setQ)} />
          <select className="input" aria-label="Filter by domain" value={domainId} onChange={reset(setDomainId)}>
            <option value="">All domains</option>{domains.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          <select className="input" aria-label="Filter by difficulty" value={difficulty} onChange={reset(setDifficulty)}>
            <option value="">Any difficulty</option><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option>
          </select>
          <select className="input" aria-label="Filter by status" value={status} onChange={reset(setStatus)}>
            <option value="">Any status</option><option value="active">Active</option><option value="inactive">Inactive</option>
          </select>
        </div>
        <Alert>{error || actionError}</Alert>
        <DataTable loading={loading} rows={items} sort={sort} onSort={onSort} empty="No problem statements yet." columns={[
          { key: 'ps_code', header: 'ID', sortKey: 'ps_code' },
          { key: 'title', header: 'Title', sortKey: 'title' },
          { key: 'domain', header: 'Domain', render: (p) => p.domain.name },
          { key: 'difficulty', header: 'Difficulty', sortKey: 'difficulty', render: (p) => <StatusBadge tone={DIFF_TONE[p.difficulty]}>{p.difficulty}</StatusBadge> },
          { key: 'files', header: 'Files', render: (p) => `${p.dataset_count} datasets · ${p.document_count} docs` },
          { key: 'status', header: 'Status', render: (p) => <StatusBadge status={p.status} /> },
          { key: 'actions', header: 'Actions', render: (p) => (
            <div className="flex gap-2">
              <Link className="btn-secondary" to={`${base}/problem-statements/${p.id}`}><Eye className="h-4 w-4" />View</Link>
              <Link className="btn-secondary" to={`${base}/problem-statements/${p.id}/edit`}><Pencil className="h-4 w-4" />Edit</Link>
              <button className="btn-secondary" onClick={() => setToggle(p)}>{p.status === 'active' ? 'Deactivate' : 'Activate'}</button>
            </div>
          ) },
        ]} />
        <Pagination meta={meta} onPage={setPage} />
      </div>
      {toggle && (
        <ConfirmDialog message={toggle.status === 'active' ? `Deactivate ${toggle.ps_code}? It can no longer be allocated.` : `Activate ${toggle.ps_code}?`}
          confirmLabel={toggle.status === 'active' ? 'Deactivate' : 'Activate'} danger={toggle.status === 'active'} busy={busy}
          onConfirm={confirmToggle} onCancel={() => setToggle(null)} />
      )}
    </div>
  )
}
