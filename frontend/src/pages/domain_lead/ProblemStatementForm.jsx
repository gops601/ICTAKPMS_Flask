import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { domainService, psService } from '../../services/adminService'
import { errorMessage, fieldErrors } from '../../services/api'
import useBasePath from '../../hooks/useBasePath'
import PageHeader from '../../components/PageHeader'
import RichTextEditor from '../../components/RichTextEditor'
import AttachmentPanel from '../../components/AttachmentPanel'
import Alert from '../../components/Alert'
import Spinner from '../../components/Spinner'

const RICH = [
  ['description', 'Project description'], ['problem_definition', 'Problem definition'],
  ['objectives', 'Project objectives'], ['scope', 'Scope'], ['expected_outcomes', 'Expected outcomes'],
  ['functional_requirements', 'Functional requirements'], ['non_functional_requirements', 'Non-functional requirements'],
  ['suggested_technologies', 'Suggested technologies'], ['dataset_info', 'Dataset information'], ['required_skills', 'Required skills'],
]
const EMPTY = {
  ps_code: '', title: '', domain_id: '', difficulty: 'medium', estimated_duration: '', status: 'active',
  ...Object.fromEntries(RICH.map(([k]) => [k, ''])),
}

export default function ProblemStatementForm() {
  const { id } = useParams()
  const editing = Boolean(id)
  const base = useBasePath()
  const navigate = useNavigate()
  const [domains, setDomains] = useState([])
  const [form, setForm] = useState(EMPTY)
  const [files, setFiles] = useState({ datasets: [], documents: [] })
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [errs, setErrs] = useState({})
  const [saved, setSaved] = useState(false)

  const load = useCallback(async () => {
    try {
      const ps = await psService.get(id)
      setForm({ ...EMPTY, ...Object.fromEntries(Object.keys(EMPTY).map((k) => [k, k === 'domain_id' ? ps.domain.id : ps[k] ?? ''])) })
      setFiles({ datasets: ps.datasets, documents: ps.documents })
    } catch (e) { setError(errorMessage(e)) }
  }, [id])

  useEffect(() => {
    (async () => {
      try {
        setDomains(await domainService.list({ active: 1 }))
        if (editing) await load()
      } catch (e) { setError(errorMessage(e)) } finally { setLoading(false) }
    })()
  }, [editing, load])

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const setRich = (k) => (html) => setForm((f) => ({ ...f, [k]: html }))

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError(''); setErrs({}); setSaved(false)
    const body = { ...form, domain_id: Number(form.domain_id), estimated_duration: form.estimated_duration || null }
    try {
      if (editing) { await psService.update(id, body); setSaved(true) }
      else {
        const created = await psService.create(body)
        navigate(`${base}/problem-statements/${created.id}/edit`, { replace: true })
      }
    } catch (err) { setError(errorMessage(err)); setErrs(fieldErrors(err)); window.scrollTo(0, 0) } finally { setBusy(false) }
  }

  if (loading) return <Spinner />
  const err = (k) => errs[k] && <p className="mt-1 text-xs text-red-600">{errs[k]}</p>

  return (
    <div className="max-w-4xl space-y-4">
      <PageHeader title={editing ? `Edit ${form.ps_code}` : 'New problem statement'}
        subtitle={editing ? 'Update details and manage datasets and reference documents.' : 'Save first; datasets and documents can be attached right after.'}
        actions={editing && <Link to={`${base}/problem-statements/${id}`} className="btn-secondary">View</Link>} />
      <form onSubmit={submit} className="card space-y-4">
        <Alert>{error}</Alert>
        {saved && <Alert type="success">Saved.</Alert>}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div><label htmlFor="ps_code" className="label">Problem statement ID *</label>
            <input id="ps_code" className="input" required disabled={editing} value={form.ps_code} onChange={set('ps_code')} />{err('ps_code')}</div>
          <div><label htmlFor="title" className="label">Project title *</label>
            <input id="title" className="input" required value={form.title} onChange={set('title')} />{err('title')}</div>
          <div><label htmlFor="domain" className="label">Domain *</label>
            <select id="domain" className="input" required value={form.domain_id} onChange={set('domain_id')}>
              <option value="">Select domain…</option>{domains.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>{err('domain')}</div>
          <div><label htmlFor="difficulty" className="label">Difficulty level</label>
            <select id="difficulty" className="input" value={form.difficulty} onChange={set('difficulty')}>
              <option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option>
            </select>{err('difficulty')}</div>
          <div><label htmlFor="duration" className="label">Estimated duration</label>
            <input id="duration" className="input" placeholder="e.g. 4 weeks" value={form.estimated_duration} onChange={set('estimated_duration')} />{err('estimated_duration')}</div>
          <div><label htmlFor="status" className="label">Status</label>
            <select id="status" className="input" value={form.status} onChange={set('status')}>
              <option value="active">Active</option><option value="inactive">Inactive</option>
            </select></div>
        </div>
        {RICH.map(([k, label]) => <RichTextEditor key={k} id={`rt-${k}`} label={label} value={form[k]} onChange={setRich(k)} error={errs[k]} />)}
        <div className="flex justify-end gap-2">
          <Link to={`${base}/problem-statements`} className="btn-secondary">Back to list</Link>
          <button className="btn-primary" disabled={busy}>{busy ? 'Saving…' : editing ? 'Save changes' : 'Create & add files'}</button>
        </div>
      </form>
      {editing && (
        <>
          <AttachmentPanel psId={id} kind="datasets" title="Datasets" canEdit items={files.datasets} onChanged={load}
            hint="CSV, TSV, XLSX, JSON, XML, TXT, ZIP, GZ, Parquet · up to 50 MB each. Add as many as needed." />
          <AttachmentPanel psId={id} kind="documents" title="Reference documents" canEdit items={files.documents} onChanged={load}
            hint="PDF, Word, PowerPoint, Excel, images, text · up to 25 MB each." />
        </>
      )}
    </div>
  )
}
