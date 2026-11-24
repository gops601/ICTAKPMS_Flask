import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { batchService, domainService, ouService } from '../../services/adminService'
import { errorMessage, fieldErrors } from '../../services/api'
import PageHeader from '../../components/PageHeader'
import DynamicField from '../../components/DynamicField'
import Alert from '../../components/Alert'
import Spinner from '../../components/Spinner'
import { downloadTextFile } from '../../services/adminService'
import { downloadCredentials } from '../../utils/credentials'

const TEMPLATE = 'Student Name,Email,Phone Number,Registration Number\r\n'
  + 'Sample Student,sample.student@example.com,9876500000,\r\n'   // the @example.com sample row is ignored on upload
const downloadStudentTemplate = () => downloadTextFile('\uFEFF' + TEMPLATE, 'student_upload_template.csv')

const blankStudent = () => ({ name: '', email: '', phone: '', registration_no: '' })
const isBlank = (r) => !r.name.trim() && !r.email.trim() && !r.phone.trim() && !r.registration_no.trim()

/** Parse pasted / uploaded rows (CSV or tab-separated, e.g. copied from Excel): name, email, phone, registration no. */
function parseStudents(text) {
  const rows = []
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim()) continue
    const sep = line.includes('\t') ? '\t' : ','
    const [name = '', email = '', phone = '', registration_no = ''] = line.split(sep).map((c) => c.trim().replace(/^"|"$/g, ''))
    if (/^(student\s*)?name$/i.test(name) && /mail/i.test(email)) continue   // header row
    if (/@example\.com$/i.test(email)) continue                                 // the template's sample row
    rows.push({ name, email, phone, registration_no })
  }
  return rows
}

/** Create / edit a batch. OU-specific inputs are rendered from the OU's configured fields. */
export default function BatchForm() {
  const { id } = useParams()
  const editing = Boolean(id)
  const navigate = useNavigate()
  const [ous, setOus] = useState([])
  const [domains, setDomains] = useState([])
  const [fields, setFields] = useState([])
  const [form, setForm] = useState({ code: '', name: '', ou_id: '', domain_id: '', subdomain_id: '', mode: '', start_date: '', end_date: '', details: {} })
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [errs, setErrs] = useState({})
  const [students, setStudents] = useState([])
  const [created, setCreated] = useState(null)

  useEffect(() => {
    (async () => {
      try {
        const [o, d] = await Promise.all([ouService.list({ active: 1 }), domainService.list({ active: 1 })])
        setOus(o); setDomains(d)
        if (editing) {
          const b = await batchService.get(id)
          setForm({ code: b.code, name: b.name, ou_id: b.ou.id, domain_id: b.domain?.id || '', subdomain_id: b.subdomain?.id || '', mode: b.mode || 'online', start_date: b.start_date || '', end_date: b.end_date || '', details: b.details })
        }
      } catch (e) { setError(errorMessage(e)) } finally { setLoading(false) }
    })()
  }, [id, editing])

  // Load the field definitions whenever the selected OU changes.
  useEffect(() => {
    if (!form.ou_id) { setFields([]); return }
    ouService.fields(form.ou_id, { scope: 'batch', active: 1 }).then(setFields).catch((e) => setError(errorMessage(e)))
  }, [form.ou_id])

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const setDetail = (key) => (value) => setForm({ ...form, details: { ...form.details, [key]: value } })

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError(''); setErrs({})
    const body = {
      name: form.name, domain_id: Number(form.domain_id), subdomain_id: form.subdomain_id ? Number(form.subdomain_id) : null, mode: form.mode,
      start_date: form.start_date || null, end_date: form.end_date || null,
      details: Object.fromEntries(fields.map((f) => [f.field_key, form.details[f.field_key] ?? ''])),
    }
    try {
      if (editing) { await batchService.update(id, body); navigate('/admin/batches') } else {
        const res = await batchService.create({ ...body, ou_id: Number(form.ou_id), students: students.filter((r) => !isBlank(r)) })
        if (res.credentials?.length) setCreated(res); else navigate('/admin/batches')
      }
    } catch (err) { setError(errorMessage(err)); setErrs(fieldErrors(err)) } finally { setBusy(false) }
  }

  const subdomains = (domains.find((d) => String(d.id) === String(form.domain_id))?.subdomains || []).filter((s) => s.is_active)
  const setRow = (i, k) => (e) => setStudents(students.map((r, j) => (j === i ? { ...r, [k]: e.target.value } : r)))
  const addPasted = (text) => { const rows = parseStudents(text); if (rows.length) setStudents([...students.filter((r) => !isBlank(r)), ...rows]) }
  const onFile = async (e) => { const f = e.target.files?.[0]; if (f) addPasted(await f.text()); e.target.value = '' }

  if (loading) return <Spinner />
  if (created) return (
    <div className="max-w-3xl">
      <PageHeader title={`Batch ${created.code} created`} subtitle={`${created.credentials.length} student(s) added. They now appear in the Students tab.`} />
      <div className="card space-y-4">
        <Alert type="success">Temporary passwords are shown only once. Download the login details now to share them.</Alert>
        <div className="flex justify-end gap-2">
          <button className="btn-primary" onClick={() => downloadCredentials(created.credentials, `${created.code}_student_credentials.csv`)}>Download login details</button>
          <button className="btn-secondary" onClick={() => navigate('/admin/students')}>Go to Students</button>
          <button className="btn-secondary" onClick={() => navigate('/admin/batches')}>Back to batches</button>
        </div>
      </div>
    </div>
  )
  const err = (k) => errs[k] && <p className="mt-1 text-xs text-red-600">{errs[k]}</p>

  return (
    <div className="max-w-3xl">
      <PageHeader title={editing ? `Edit batch ${form.code}` : 'New batch'} subtitle="Fields below depend on the selected OU." />
      <form onSubmit={submit} className="card space-y-4">
        <Alert>{error}</Alert>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="ou" className="label">Organisational unit *</label>
            <select id="ou" className="input" required disabled={editing} value={form.ou_id}
              onChange={(e) => setForm({ ...form, ou_id: e.target.value, details: {} })}>
              <option value="">Select OU…</option>{ous.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
            {err('ou_id')}
          </div>
          <div>
            <label htmlFor="dom" className="label">Domain *</label>
            <select id="dom" className="input" required value={form.domain_id} onChange={(e) => setForm({ ...form, domain_id: e.target.value, subdomain_id: '' })}>
              <option value="">Select domain…</option>{domains.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
            {err('domain')}{err('domain_id')}
          </div>
          <div>
            <label htmlFor="subdom" className="label">SubDomain</label>
            <select id="subdom" className="input" value={form.subdomain_id} onChange={set('subdomain_id')} disabled={!form.domain_id}>
              <option value="">{form.domain_id ? (subdomains.length ? 'Select subdomain…' : 'No subdomains in this domain') : 'Select a domain first'}</option>
              {subdomains.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            {err('subdomain')}
          </div>
          <div>
            <label htmlFor="domid" className="label">Domain ID</label>
            <input id="domid" className="input bg-slate-50" readOnly value={form.domain_id} placeholder="Filled in from the domain" />
          </div>
          <div>
            <label htmlFor="mode" className="label">Batch mode *</label>
            <select id="mode" className="input" required value={form.mode} onChange={set('mode')}>
              <option value="">Select online or offline…</option>
              <option value="online">Online – 4 weeks</option>
              <option value="offline">Offline – 3 weeks</option>
            </select>
            {err('mode')}
            <p className="mt-1 text-xs text-slate-500">Week 1 is SRS submission and datasets, then implementation: 2 weeks offline, 3 weeks online. It applies to every project and student of the batch.</p>
          </div>
          <div>
            <label htmlFor="code" className="label">Batch ID</label>
            <input id="code" className="input bg-slate-50" readOnly value={editing ? form.code : ''}
              placeholder="Generated automatically (e.g. ACADEMIC_ONLINE_0001)" />
            {!editing && <p className="mt-1 text-xs text-slate-500">Issued when you save, based on the domain's short code.</p>}
          </div>
          <div>
            <label htmlFor="name" className="label">Batch name *</label>
            <input id="name" className="input" required value={form.name} onChange={set('name')} />{err('name')}
          </div>
          <div>
            <label htmlFor="sd" className="label">Start date</label>
            <input id="sd" type="date" className="input" value={form.start_date} onChange={set('start_date')} />{err('start_date')}
          </div>
          <div>
            <label htmlFor="ed" className="label">End date</label>
            <input id="ed" type="date" className="input" value={form.end_date} onChange={set('end_date')} />{err('end_date')}
          </div>
        </div>
        {fields.length > 0 && (
          <fieldset className="border-t border-slate-200 pt-4">
            <legend className="px-1 text-sm font-semibold text-slate-700">OU details</legend>
            <div className="mt-2 grid grid-cols-1 gap-4 sm:grid-cols-2">
              {fields.map((f) => (
                <DynamicField key={f.id} field={f} value={form.details[f.field_key]} onChange={setDetail(f.field_key)} error={errs[`details.${f.field_key}`]} />
              ))}
            </div>
          </fieldset>
        )}
        {!editing && (
          <fieldset className="border-t border-slate-200 pt-4">
            <legend className="px-1 text-sm font-semibold text-slate-700">Students (optional)</legend>
            <p className="text-xs text-slate-500">Add students now; they are created with the batch and appear in the Students tab. Leave the registration number blank to have it generated.</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <button type="button" className="btn-secondary" onClick={() => setStudents([...students, blankStudent()])}>Add student</button>
              <button type="button" className="btn-secondary" onClick={downloadStudentTemplate}>Download CSV template</button>
              <label className="btn-secondary cursor-pointer">Upload CSV<input type="file" accept=".csv,.txt,.tsv" className="hidden" onChange={onFile} /></label>
            </div>
            <textarea className="input mt-2 h-20 font-mono text-xs" aria-label="Paste students"
              placeholder="Or paste rows from Excel / CSV: name, email, phone, registration no (one student per line)"
              onPaste={(e) => { e.preventDefault(); addPasted(e.clipboardData.getData('text')) }} onChange={() => {}} value="" />
            {students.length > 0 && (
              <div className="mt-2 space-y-2">
                {students.map((r, i) => (
                  <div key={i} className="grid grid-cols-2 gap-2 sm:grid-cols-[1fr_1.2fr_1fr_1fr_auto]">
                    <input className="input" placeholder="Name" aria-label={`Student ${i + 1} name`} value={r.name} onChange={setRow(i, 'name')} />
                    <input className="input" placeholder="Email" aria-label={`Student ${i + 1} email`} value={r.email} onChange={setRow(i, 'email')} />
                    <input className="input" placeholder="Phone" aria-label={`Student ${i + 1} phone`} value={r.phone} onChange={setRow(i, 'phone')} />
                    <input className="input" placeholder="Reg. no (auto)" aria-label={`Student ${i + 1} registration number`} value={r.registration_no} onChange={setRow(i, 'registration_no')} />
                    <button type="button" className="btn-secondary" onClick={() => setStudents(students.filter((_, j) => j !== i))}>Remove</button>
                    {['name', 'email', 'phone', 'registration_no'].map((k) => err(`students.${i + 1}.${k}`))}
                  </div>
                ))}
                <p className="text-xs text-slate-500">{students.filter((r) => !isBlank(r)).length} student(s) will be added.</p>
              </div>
            )}
          </fieldset>
        )}
        <div className="flex justify-end gap-2">
          <Link to="/admin/batches" className="btn-secondary">Cancel</Link>
          <button className="btn-primary" disabled={busy}>{busy ? 'Saving…' : editing ? 'Save changes' : 'Create batch'}</button>
        </div>
      </form>
    </div>
  )
}
