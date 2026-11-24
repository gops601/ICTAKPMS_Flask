import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { batchService, domainService, ouService } from '../../services/adminService'
import { errorMessage, fieldErrors } from '../../services/api'
import PageHeader from '../../components/PageHeader'
import DynamicField from '../../components/DynamicField'
import Alert from '../../components/Alert'
import Spinner from '../../components/Spinner'

/** Create / edit a batch. OU-specific inputs are rendered from the OU's configured fields. */
export default function BatchForm() {
  const { id } = useParams()
  const editing = Boolean(id)
  const navigate = useNavigate()
  const [ous, setOus] = useState([])
  const [domains, setDomains] = useState([])
  const [fields, setFields] = useState([])
  const [form, setForm] = useState({ code: '', name: '', ou_id: '', domain_id: '', mode: '', start_date: '', end_date: '', details: {} })
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [errs, setErrs] = useState({})

  useEffect(() => {
    (async () => {
      try {
        const [o, d] = await Promise.all([ouService.list({ active: 1 }), domainService.list({ active: 1 })])
        setOus(o); setDomains(d)
        if (editing) {
          const b = await batchService.get(id)
          setForm({ code: b.code, name: b.name, ou_id: b.ou.id, domain_id: b.domain?.id || '', mode: b.mode || 'online', start_date: b.start_date || '', end_date: b.end_date || '', details: b.details })
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
      name: form.name, domain_id: Number(form.domain_id), mode: form.mode,
      start_date: form.start_date || null, end_date: form.end_date || null,
      details: Object.fromEntries(fields.map((f) => [f.field_key, form.details[f.field_key] ?? ''])),
    }
    try {
      if (editing) await batchService.update(id, body)
      else await batchService.create({ ...body, ou_id: Number(form.ou_id) })
      navigate('/admin/batches')
    } catch (err) { setError(errorMessage(err)); setErrs(fieldErrors(err)) } finally { setBusy(false) }
  }

  if (loading) return <Spinner />
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
            <select id="dom" className="input" required value={form.domain_id} onChange={set('domain_id')}>
              <option value="">Select domain…</option>{domains.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
            {err('domain')}{err('domain_id')}
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
              placeholder="Generated automatically (ICT_<domain>_…)" />
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
        <div className="flex justify-end gap-2">
          <Link to="/admin/batches" className="btn-secondary">Cancel</Link>
          <button className="btn-primary" disabled={busy}>{busy ? 'Saving…' : editing ? 'Save changes' : 'Create batch'}</button>
        </div>
      </form>
    </div>
  )
}
