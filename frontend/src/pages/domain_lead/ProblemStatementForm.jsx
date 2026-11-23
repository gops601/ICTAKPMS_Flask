import { useCallback, useEffect, useState } from 'react'
import { Plus } from 'lucide-react'
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
  ps_code: '', title: '', domain_id: '', subdomain_id: '', source_type: 'internal', industry: '', difficulty: 'medium', estimated_duration: '', status: 'active',
  ...Object.fromEntries(RICH.map(([k]) => [k, ''])),
}

export default function ProblemStatementForm() {
  const { id } = useParams()
  const editing = Boolean(id)
  const base = useBasePath()
  const navigate = useNavigate()
  const [domains, setDomains] = useState([])
  const [industries, setIndustries] = useState([])
  const [newSub, setNewSub] = useState('')
  const [subBusy, setSubBusy] = useState(false)
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
      setForm({ ...EMPTY, ...Object.fromEntries(Object.keys(EMPTY).map((k) => [k, k === 'domain_id' ? ps.domain.id : k === 'subdomain_id' ? ps.subdomain?.id ?? '' : ps[k] ?? ''])) })
      setFiles({ datasets: ps.datasets, documents: ps.documents })
    } catch (e) { setError(errorMessage(e)) }
  }, [id])

  useEffect(() => {
    (async () => {
      try {
        setDomains(await domainService.list({ active: 1 }))
        psService.industries().then(setIndustries).catch(() => {})
        if (editing) await load()
      } catch (e) { setError(errorMessage(e)) } finally { setLoading(false) }
    })()
  }, [editing, load])

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const domain = domains.find((d) => String(d.id) === String(form.domain_id))
  const subdomains = (domain?.subdomains || []).filter((s) => s.is_active || String(s.id) === String(form.subdomain_id))
  const needsSub = (domain?.subdomains || []).some((s) => s.is_active)
  const addSubdomain = async () => {
    if (newSub.trim().length < 2) return
    setSubBusy(true); setError('')
    try {
      const sd = await domainService.addSubdomain(domain.id, newSub)
      setDomains((list) => list.map((d) => (d.id === domain.id ? { ...d, subdomains: [...(d.subdomains || []), sd] } : d)))
      setForm((f) => ({ ...f, subdomain_id: sd.id })); setNewSub('')
    } catch (e) { setError(errorMessage(e)) } finally { setSubBusy(false) }
  }
  const setRich = (k) => (html) => setForm((f) => ({ ...f, [k]: html }))

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError(''); setErrs({}); setSaved(false)
    const body = { ...form, domain_id: Number(form.domain_id), subdomain_id: form.subdomain_id ? Number(form.subdomain_id) : null, estimated_duration: form.estimated_duration || null,
      industry: form.source_type === 'industry' ? form.industry : null }
    try {
      if (editing) { await psService.update(id, body); setSaved(true) }
      else {
        const created = await psService.create(body)
        navigate(`${base}/project-shelf/${created.id}/edit`, { replace: true })
      }
    } catch (err) { setError(errorMessage(err)); setErrs(fieldErrors(err)); window.scrollTo(0, 0) } finally { setBusy(false) }
  }

  if (loading) return <Spinner />
  const err = (k) => errs[k] && <p className="mt-1 text-xs text-red-600">{errs[k]}</p>

  return (
    <div className="max-w-4xl space-y-4">
      <PageHeader title={editing ? `Edit ${form.ps_code}` : 'New project'}
        subtitle={editing ? 'Update details and manage datasets and reference documents.' : 'Save first; datasets and documents can be attached right after.'}
        actions={editing && <Link to={`${base}/project-shelf/${id}`} className="btn-secondary">View</Link>} />
      <form onSubmit={submit} className="card space-y-4">
        <Alert>{error}</Alert>
        {saved && <Alert type="success">Saved.</Alert>}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div><label htmlFor="ps_code" className="label">Project ID</label>
            <input id="ps_code" className="input" disabled={editing} placeholder="Leave blank to auto-generate (ICT_PS_…)" value={form.ps_code} onChange={set('ps_code')} />{err('ps_code')}</div>
          <div><label htmlFor="title" className="label">Project title *</label>
            <input id="title" className="input" required value={form.title} onChange={set('title')} />{err('title')}</div>
          <div><label htmlFor="domain" className="label">Domain *</label>
            <select id="domain" className="input" required value={form.domain_id} onChange={set('domain_id')}>
              <option value="">Select domain…</option>{domains.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>{err('domain')}</div>
          <div><label htmlFor="subdomain" className="label">Subdomain{needsSub ? ' *' : ''}</label>
            <select id="subdomain" className="input" required={needsSub} disabled={!domain} value={form.subdomain_id} onChange={set('subdomain_id')}>
              <option value="">{!domain ? 'Choose a domain first' : needsSub ? 'Select subdomain…' : 'None (no subdomains yet)'}</option>
              {subdomains.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>{err('subdomain_id')}
            {domain && (
              <div className="mt-2 flex gap-2">
                <input className="input" placeholder="Add a new subdomain…" aria-label="New subdomain" value={newSub} onChange={(e) => setNewSub(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addSubdomain() } }} />
                <button type="button" className="btn-secondary shrink-0" disabled={subBusy || newSub.trim().length < 2} onClick={addSubdomain}><Plus className="h-4 w-4" />Add</button>
              </div>
            )}</div>
          <div><label htmlFor="source_type" className="label">Statement type *</label>
            <select id="source_type" className="input" value={form.source_type} onChange={set('source_type')}>
              <option value="internal">Internal statement</option><option value="industry">Industry statement</option>
            </select>{err('source_type')}</div>
          {form.source_type === 'industry' && (
            <div><label htmlFor="industry" className="label">Industry *</label>
              <input id="industry" className="input" required list="industry-options" placeholder="e.g. Healthcare, Finance" value={form.industry} onChange={set('industry')} />
              <datalist id="industry-options">{industries.map((i) => <option key={i} value={i} />)}</datalist>{err('industry')}</div>
          )}
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
          <Link to={`${base}/project-shelf`} className="btn-secondary">Back to Project Shelf</Link>
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
