import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Download, KeyRound, Plus, Upload } from 'lucide-react'
import { batchService, studentService } from '../../services/adminService'
import { errorMessage, fieldErrors } from '../../services/api'
import { useDebounced, useList } from '../../hooks/useList'
import PageHeader from '../../components/PageHeader'
import DataTable from '../../components/DataTable'
import Pagination from '../../components/Pagination'
import Modal from '../../components/Modal'
import Alert from '../../components/Alert'
import { downloadCredentials, rowFromStudent } from '../../utils/credentials'

function AddStudentModal({ batches, onClose, onSaved }) {
  const [form, setForm] = useState({ name: '', email: '', phone: '', registration_no: '', batch_id: '' })
  const [error, setError] = useState('')
  const [errs, setErrs] = useState({})
  const [busy, setBusy] = useState(false)
  const [created, setCreated] = useState(null)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError(''); setErrs({})
    try { setCreated(await studentService.create({ ...form, batch_id: Number(form.batch_id), phone: form.phone || null })) }
    catch (err) { setError(errorMessage(err)); setErrs(fieldErrors(err)) } finally { setBusy(false) }
  }

  if (created) {
    return (
      <Modal title="Student created" onClose={onSaved}>
        <Alert type="warning">Temporary password (shown once): <b className="font-mono">{created.temporary_password}</b></Alert>
        <p className="mt-3 text-sm text-slate-600">{created.name} must change this password at first login.</p>
        <div className="mt-4 flex justify-end gap-2">
          <button className="btn-secondary" onClick={() => downloadCredentials([rowFromStudent(created)], `${created.registration_no}_login_details.csv`)}><Download className="h-4 w-4" />Download login details</button>
          <button className="btn-primary" onClick={onSaved}>Done</button>
        </div>
      </Modal>
    )
  }
  const err = (k) => errs[k] && <p className="mt-1 text-xs text-red-600">{errs[k]}</p>
  return (
    <Modal title="Add student" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <Alert>{error}</Alert>
        <div><label htmlFor="s-batch" className="label">Batch *</label>
          <select id="s-batch" className="input" required value={form.batch_id} onChange={set('batch_id')}>
            <option value="">Select batch…</option>{batches.map((b) => <option key={b.id} value={b.id}>{b.code} – {b.name}</option>)}
          </select>{err('batch_id')}</div>
        <div><label htmlFor="s-name" className="label">Name *</label><input id="s-name" className="input" required value={form.name} onChange={set('name')} />{err('name')}</div>
        <div><label htmlFor="s-email" className="label">Email *</label><input id="s-email" type="email" className="input" required value={form.email} onChange={set('email')} />{err('email')}</div>
        <div><label htmlFor="s-phone" className="label">Phone</label><input id="s-phone" className="input" value={form.phone} onChange={set('phone')} /></div>
        <div><label htmlFor="s-reg" className="label">Registration number *</label><input id="s-reg" className="input" required value={form.registration_no} onChange={set('registration_no')} /></div>
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Create student'}</button>
        </div>
      </form>
    </Modal>
  )
}

function CredentialsModal({ batches, onClose }) {
  const [batchId, setBatchId] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const issue = async () => {
    setBusy(true); setError('')
    try { setResult(await studentService.credentials(Number(batchId))) } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }

  return (
    <Modal title="Download student credentials" onClose={onClose} wide>
      {!result ? (
        <div className="space-y-4">
          <Alert>{error}</Alert>
          <p className="text-sm text-slate-600">
            Creates a <b>new temporary password</b> for every student in the batch who has not logged in yet, and gives you a file with each
            student&apos;s login details to share. Students who already chose their own password are not touched. Passwords are shown once and are not stored in readable form.
          </p>
          <div>
            <label htmlFor="cred-batch" className="label">Batch</label>
            <select id="cred-batch" className="input" value={batchId} onChange={(e) => setBatchId(e.target.value)}>
              <option value="">Select batch…</option>{batches.map((b) => <option key={b.id} value={b.id}>{b.code} – {b.name}</option>)}
            </select>
          </div>
          <div className="flex justify-end gap-2">
            <button className="btn-secondary" onClick={onClose}>Cancel</button>
            <button className="btn-primary" disabled={!batchId || busy} onClick={issue}><KeyRound className="h-4 w-4" />{busy ? 'Generating…' : 'Generate passwords'}</button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <Alert type={result.credentials.length ? 'success' : 'warning'}>
            {result.credentials.length ? `${result.credentials.length} student(s) ready for batch ${result.batch.code}.` : 'No new passwords were issued.'}
            {result.skipped.length > 0 && ` ${result.skipped.length} skipped.`}
          </Alert>
          {result.credentials.length > 0 && (
            <>
              <Alert type="warning">Download now – these passwords cannot be shown again. Students must change them at first login.</Alert>
              <button className="btn-primary" onClick={() => downloadCredentials(result.credentials, `${result.batch.code}_student_credentials.csv`)}>
                <Download className="h-4 w-4" />Download student details with passwords (CSV)
              </button>
            </>
          )}
          {result.skipped.length > 0 && (
            <ul className="list-disc pl-5 text-sm text-slate-600" aria-label="Skipped students">
              {result.skipped.map((s) => <li key={s.registration_no}>{s.name} ({s.registration_no}) – {s.reason}</li>)}
            </ul>
          )}
          <div className="flex justify-end"><button className="btn-secondary" onClick={onClose}>Close</button></div>
        </div>
      )}
    </Modal>
  )
}

export default function StudentManagement() {
  const [q, setQ] = useState('')
  const [batchId, setBatchId] = useState('')
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState({ key: 'name', order: 'asc' })
  const [batches, setBatches] = useState([])
  const [searchParams] = useSearchParams()
  const [adding, setAdding] = useState(searchParams.get('add') === '1')
  const [credentials, setCredentials] = useState(false)
  const dq = useDebounced(q)

  useEffect(() => { batchService.list({ per_page: 100, status: 'active' }).then((r) => setBatches(r.items)).catch(() => {}) }, [])
  const { items, meta, loading, error, reload } = useList(studentService.list, {
    q: dq, batch_id: batchId || undefined, page, sort: sort.key, order: sort.order,
  })
  const onSort = (key) => setSort((s) => ({ key, order: s.key === key && s.order === 'asc' ? 'desc' : 'asc' }))

  return (
    <div>
      <PageHeader title="Students" subtitle="Students across all batches."
        actions={<>
          <button className="btn-secondary" onClick={() => setCredentials(true)}><KeyRound className="h-4 w-4" />Download credentials</button>
          <Link to="/admin/uploads?tab=students" className="btn-secondary"><Upload className="h-4 w-4" />Bulk upload</Link>
          <button className="btn-primary" onClick={() => setAdding(true)}><Plus className="h-4 w-4" />Add student</button>
        </>} />
      <div className="card">
        <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <input className="input" placeholder="Search name, email or reg. no…" aria-label="Search students" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} />
          <select className="input" aria-label="Filter by batch" value={batchId} onChange={(e) => { setBatchId(e.target.value); setPage(1) }}>
            <option value="">All batches</option>{batches.map((b) => <option key={b.id} value={b.id}>{b.code} – {b.name}</option>)}
          </select>
        </div>
        <Alert>{error}</Alert>
        <DataTable loading={loading} rows={items} sort={sort} onSort={onSort} columns={[
          { key: 'name', header: 'Name', sortKey: 'name' },
          { key: 'email', header: 'Email' },
          { key: 'registration_no', header: 'Reg. no', sortKey: 'registration_no' },
          { key: 'batch', header: 'Batch', render: (s) => s.batch.code },
          { key: 'phone', header: 'Phone', render: (s) => s.phone || '—' },
        ]} />
        <Pagination meta={meta} onPage={setPage} />
      </div>
      {credentials && <CredentialsModal batches={batches} onClose={() => setCredentials(false)} />}
      {adding && <AddStudentModal batches={batches} onClose={() => setAdding(false)} onSaved={() => { setAdding(false); reload() }} />}
    </div>
  )
}
