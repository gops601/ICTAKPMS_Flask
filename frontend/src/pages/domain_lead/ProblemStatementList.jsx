import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Eye, Pencil, Plus, Trash2, Upload } from 'lucide-react'
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
import ShelfReviewButtons from '../../components/ShelfReviewButtons'

const DIFF_TONE = { easy: 'green', medium: 'orange', hard: 'red' }

export default function ProblemStatementList() {
  const base = useBasePath()
  const readOnly = base === '/mentor'  // mentors browse the shelf; leads and admins manage it
  const [q, setQ] = useState('')
  const [domainId, setDomainId] = useState('')
  const [difficulty, setDifficulty] = useState('')
  const [status, setStatus] = useState('')
  const [sourceType, setSourceType] = useState('')
  const [industry, setIndustry] = useState('')
  const [subdomainId, setSubdomainId] = useState('')
  const [approval, setApproval] = useState('')
  const [industries, setIndustries] = useState([])
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState({ key: 'created', order: 'desc' })
  const [domains, setDomains] = useState([])
  const [toggle, setToggle] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const dq = useDebounced(q)

  useEffect(() => { domainService.list().then(setDomains).catch(() => {}); psService.industries().then(setIndustries).catch(() => {}) }, [])
  const { items, meta, loading, error, reload } = useList(psService.list, {
    q: dq, domain_id: domainId || undefined, difficulty: difficulty || undefined, status: status || undefined,
    source_type: sourceType || undefined, industry: industry || undefined, subdomain_id: subdomainId || undefined, approval_status: approval || undefined,
    page, sort: sort.key, order: sort.order,
  })
  const changeType = (e) => { setSourceType(e.target.value); if (e.target.value === 'internal') setIndustry(''); setPage(1) }
  const reset = (fn) => (e) => { fn(e.target.value); setPage(1) }
  const onSort = (key) => setSort((s) => ({ key, order: s.key === key && s.order === 'asc' ? 'desc' : 'asc' }))

  const confirmToggle = async () => {
    setBusy(true)
    try { await psService.setStatus(toggle.id, toggle.status === 'active' ? 'inactive' : 'active'); setToggle(null); reload() }
    catch (e) { setActionError(errorMessage(e)); setToggle(null) } finally { setBusy(false) }
  }

  const confirmDelete = async () => {
    setBusy(true); setActionError('')
    try { await psService.remove(deleting.id); setDeleting(null); reload() }
    catch (e) { setActionError(errorMessage(e)); setDeleting(null) } finally { setBusy(false) }
  }

  return (
    <div>
      <PageHeader title="Project Shelf" subtitle={readOnly ? 'Every project on the shelf for the domains of your batches.' : 'Every project created for your domain(s), ready to be allocated.'}
        actions={!readOnly && <>
          <Link to={`${base}/project-shelf/upload`} className="btn-secondary"><Upload className="h-4 w-4" />Bulk upload</Link>
          <Link to={`${base}/project-shelf/new`} className="btn-primary"><Plus className="h-4 w-4" />New project</Link>
        </>} />
      <div className="card">
        <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <input className="input" placeholder="Search title or ID…" aria-label="Search projects" value={q} onChange={reset(setQ)} />
          <select className="input" aria-label="Filter by domain" value={domainId} onChange={reset(setDomainId)}>
            <option value="">All domains</option>{domains.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          <select className="input" aria-label="Filter by subdomain" value={subdomainId} onChange={reset(setSubdomainId)}>
            <option value="">All subdomains</option>
            {domains.filter((d) => !domainId || String(d.id) === String(domainId)).flatMap((d) => (d.subdomains || []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>))}
          </select>
          <select className="input" aria-label="Filter by approval" value={approval} onChange={reset(setApproval)}>
            <option value="">Any approval</option><option value="approved">Approved</option><option value="pending">Awaiting mentor approval</option><option value="rejected">Rejected</option>
          </select>
          <select className="input" aria-label="Filter by statement type" value={sourceType} onChange={changeType}>
            <option value="">All types</option><option value="internal">Internal</option><option value="industry">Industry</option>
          </select>
          <select className="input" aria-label="Filter by industry" value={industry} disabled={sourceType === 'internal'} onChange={reset(setIndustry)}>
            <option value="">All industries</option>{industries.map((i) => <option key={i} value={i}>{i}</option>)}
          </select>
          <select className="input" aria-label="Filter by difficulty" value={difficulty} onChange={reset(setDifficulty)}>
            <option value="">Any difficulty</option><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option>
          </select>
          <select className="input" aria-label="Filter by status" value={status} onChange={reset(setStatus)}>
            <option value="">Any status</option><option value="active">Active</option><option value="inactive">Inactive</option>
          </select>
        </div>
        <Alert>{error || actionError}</Alert>
        <DataTable loading={loading} rows={items} sort={sort} onSort={onSort} empty="No projects on the shelf yet." columns={[
          { key: 'ps_code', header: 'ID', sortKey: 'ps_code' },
          { key: 'title', header: 'Title', sortKey: 'title', render: (p) => <div>{p.title}{p.proposed_by && <div className="text-xs text-green-700">Student project · {p.proposed_by.name}{p.proposal?.is_group ? ` + ${p.proposal.members.length - 1} (group)` : ''}</div>}
          {p.approval_status && p.approval_status !== 'approved' && <StatusBadge tone={p.approval_status === 'pending' ? 'orange' : 'red'}>{p.approval_status === 'pending' ? 'Awaiting mentor approval' : p.approval_status}</StatusBadge>}</div> },
          { key: 'domain', header: 'Domain', render: (p) => <div>{p.domain.name}{p.subdomain && <div className="text-xs text-slate-500">{p.subdomain.name}</div>}</div> },
          { key: 'source_type', header: 'Type', render: (p) => (p.source_type === 'industry'
            ? <div><StatusBadge tone="blue">Industry</StatusBadge><div className="mt-0.5 text-xs text-slate-500">{p.industry}</div></div>
            : <StatusBadge tone="green">Internal</StatusBadge>) },
          { key: 'difficulty', header: 'Difficulty', sortKey: 'difficulty', render: (p) => <StatusBadge tone={DIFF_TONE[p.difficulty]}>{p.difficulty}</StatusBadge> },
          { key: 'files', header: 'Files', render: (p) => `${p.dataset_count} datasets · ${p.document_count} docs` },
          { key: 'status', header: 'Status', render: (p) => <StatusBadge status={p.status} /> },
          { key: 'actions', header: 'Actions', render: (p) => (
            <div className="flex flex-wrap gap-2">
              <Link className="btn-secondary" to={`${base}/project-shelf/${p.id}`}><Eye className="h-4 w-4" />View</Link>
              <ShelfReviewButtons ps={p} onDone={reload} />
              {!readOnly && <Link className="btn-secondary" to={`${base}/project-shelf/${p.id}/edit`}><Pencil className="h-4 w-4" />Edit</Link>}
              {!readOnly && <button className="btn-secondary" onClick={() => setToggle(p)}>{p.status === 'active' ? 'Deactivate' : 'Activate'}</button>}
              {!readOnly && <button className="btn-danger" aria-label={`Delete ${p.ps_code}`} onClick={() => { setActionError(''); setDeleting(p) }}><Trash2 className="h-4 w-4" />Delete</button>}
            </div>
          ) },
        ]} />
        <Pagination meta={meta} onPage={setPage} />
      </div>
      {deleting && (
        <ConfirmDialog danger confirmLabel="Delete permanently" busy={busy} onConfirm={confirmDelete} onCancel={() => setDeleting(null)}
          message={`Permanently delete ${deleting.ps_code} – ${deleting.title}, with its datasets and documents? This cannot be undone. Projects already allocated from it block deletion (deactivate it instead).`} />
      )}
      {toggle && (
        <ConfirmDialog message={toggle.status === 'active' ? `Deactivate ${toggle.ps_code}? It can no longer be allocated.` : `Activate ${toggle.ps_code}?`}
          confirmLabel={toggle.status === 'active' ? 'Deactivate' : 'Activate'} danger={toggle.status === 'active'} busy={busy}
          onConfirm={confirmToggle} onCancel={() => setToggle(null)} />
      )}
    </div>
  )
}
