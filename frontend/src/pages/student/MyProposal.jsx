import { useCallback, useEffect, useRef, useState } from 'react'
import { Download, Upload } from 'lucide-react'
import { proposalService } from '../../services/adminService'
import { errorMessage, fieldErrors } from '../../services/api'
import PageHeader from '../../components/PageHeader'
import StatusBadge from '../../components/StatusBadge'
import Alert from '../../components/Alert'
import Spinner from '../../components/Spinner'
import DataCollectionTable from '../../components/DataCollectionTable'
import TeamPicker from '../../components/TeamPicker'

const TONE = { pending: 'orange', approved: 'green', rejected: 'red', withdrawn: 'grey' }

/** Students propose their own detailed problem statement; a mentor must approve it. Locked once a project is allocated. */
export default function MyProposal() {
  const fileRef = useRef(null)
  const [info, setInfo] = useState(null)
  const [form, setForm] = useState({ title: '', summary: '' })
  const [file, setFile] = useState(null)
  const [datasets, setDatasets] = useState([])
  const [subdomainId, setSubdomainId] = useState('')
  const dsRef = useRef(null)
  const sheetRef = useRef(null)
  const [sheet, setSheet] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [errs, setErrs] = useState({})
  const [done, setDone] = useState(false)
  const [mode, setMode] = useState('individual')          // individual | group
  const [mates, setMates] = useState(null)               // { me, max_group_size, students } once Group is chosen
  const [myRole, setMyRole] = useState('')
  const [team, setTeam] = useState([])

  const load = useCallback(() => proposalService.mine().then(setInfo).catch((e) => setError(errorMessage(e))), [])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (mode === 'group' && mates === null) proposalService.classmates().then(setMates).catch((e) => { setError(errorMessage(e)); setMates({ me: null, max_group_size: 6, students: [] }) })
  }, [mode, mates])

  const submit = async (e) => {
    e.preventDefault()
    if (!file) return setError('Choose the detailed proposal document first.')
    if (datasets.length && !sheet) return setError('Upload the filled data collection sheet (Excel) that describes your datasets.')
    if (mode === 'group' && team.length === 0) return setError('Select the students who are in your group.')
    setBusy(true); setError(''); setErrs({}); setDone(false)
    try {
      const members = mates?.me ? [{ student_id: mates.me, role: myRole }, ...team] : team
      await proposalService.submit(form.title, form.summary, file, datasets, subdomainId || null, sheet, mode, members)
      setMode('individual'); setMates(null); setTeam([]); setMyRole('')
      setForm({ title: '', summary: '' }); setFile(null); setDatasets([]); setSheet(null); setSubdomainId(''); setDone(true)
      if (sheetRef.current) sheetRef.current.value = ''
      if (fileRef.current) fileRef.current.value = ''
      if (dsRef.current) dsRef.current.value = ''
      await load()
    } catch (err) { setError(errorMessage(err)); setErrs(fieldErrors(err)) } finally { setBusy(false) }
  }
  const download = async (p) => { try { await proposalService.download(p) } catch (e) { setError(errorMessage(e, 'Download failed')) } }

  if (!info) return error ? <Alert>{error}</Alert> : <Spinner />
  const locked = !info.can_upload

  return (
    <div className="max-w-3xl space-y-4">
      <PageHeader title="My Project Proposal" subtitle="Add your project details and datasets. They go onto the Project Shelf straight away; once your mentor approves, your project starts and you can submit the SRS." />
      <Alert>{error}</Alert>
      {done && <Alert type="success">Added to the Project Shelf. Your mentor has been notified; the SRS opens once they approve it.</Alert>}
      {locked && <Alert type={info.has_project ? 'warning' : 'info'}>{info.blocked_reason}</Alert>}

      <div className="card flex flex-wrap items-center justify-between gap-3" aria-label="Sample project template">
        <div className="min-w-0 text-sm">
          <div className="font-medium text-slate-900">Sample project template</div>
          <p className="text-xs text-slate-500">The same template the Project Shelf uses: title, description, problem definition, objectives, scope, outcomes, requirements, technologies and more. Use it to plan your proposal.</p>
        </div>
        <div className="flex gap-2">
          <button type="button" className="btn-secondary" onClick={() => proposalService.projectTemplate('xlsx').catch((e) => setError(errorMessage(e, 'Download failed')))}><Download className="h-4 w-4" />Excel</button>
          <button type="button" className="btn-secondary" onClick={() => proposalService.projectTemplate('csv').catch((e) => setError(errorMessage(e, 'Download failed')))}><Download className="h-4 w-4" />CSV</button>
        </div>
      </div>

      <form onSubmit={submit} className="card space-y-3" aria-label="Upload project proposal">
        <fieldset disabled={locked || busy} className="space-y-3 disabled:opacity-60">
          <fieldset className="rounded-lg border border-slate-200 p-3">
            <legend className="label !mb-0 px-1">Project type</legend>
            <div className="flex flex-wrap gap-5 text-sm">
              <label className="flex items-center gap-2"><input type="radio" name="pp-mode" checked={mode === 'individual'} onChange={() => setMode('individual')} />Individual project</label>
              <label className="flex items-center gap-2"><input type="radio" name="pp-mode" checked={mode === 'group'} onChange={() => setMode('group')} />Group project</label>
            </div>
            {mode === 'group' && (
              <div className="mt-3 space-y-3">
                {mates === null ? <p className="text-sm text-slate-500">Loading your batch mates…</p> : (
                  <>
                    <div>
                      <label htmlFor="pp-myrole" className="label">Your role in the group</label>
                      <input id="pp-myrole" className="input !w-60" placeholder="Team Lead" maxLength={60} value={myRole} onChange={(e) => setMyRole(e.target.value)} />
                    </div>
                    <div>
                      <div className="label">Select your team mates and give each a role <span className="font-normal text-slate-500">({team.length + 1} of up to {mates.max_group_size} students, including you)</span></div>
                      <TeamPicker students={mates.students} members={team} onChange={setTeam} max={mates.max_group_size - 1} idPrefix="pp" />
                      {errs.members && <p className="mt-1 text-xs text-red-600">{Array.isArray(errs.members) ? errs.members.join('; ') : errs.members}</p>}
                    </div>
                    <p className="text-xs text-slate-500">Only students without a project of their own are listed. Once submitted, the group can only be changed by your mentor or Domain Lead.</p>
                  </>
                )}
              </div>
            )}
          </fieldset>
          <div><label htmlFor="pp-title" className="label">Title *</label>
            <input id="pp-title" className="input" required maxLength={255} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
            {errs.title && <p className="mt-1 text-xs text-red-600">{errs.title}</p>}</div>
          <div><label htmlFor="pp-sum" className="label">Short summary</label>
            <textarea id="pp-sum" className="input min-h-[80px]" value={form.summary} onChange={(e) => setForm({ ...form, summary: e.target.value })} /></div>
          {info.domain && (
            <div><label htmlFor="pp-sub" className="label">Subdomain{info.subdomains.length ? ' *' : ''} <span className="font-normal text-slate-500">· {info.domain.name}</span></label>
              <select id="pp-sub" className="input" required={info.subdomains.length > 0} disabled={info.subdomains.length === 0} value={subdomainId} onChange={(e) => setSubdomainId(e.target.value)}>
                <option value="">{info.subdomains.length ? 'Select subdomain…' : 'No subdomains in this domain'}</option>
                {info.subdomains.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
              {errs.subdomain_id && <p className="mt-1 text-xs text-red-600">{errs.subdomain_id}</p>}</div>
          )}
          <div><label htmlFor="pp-file" className="label">Detailed project proposal *</label>
            <input id="pp-file" ref={fileRef} type="file" className="text-sm" onChange={(e) => setFile(e.target.files?.[0] || null)} />
            <p className="mt-1 text-xs text-slate-500">PDF, Word, PowerPoint, Excel, images or text · up to 25 MB.</p></div>
          <div><label htmlFor="pp-ds" className="label">Datasets <span className="font-normal text-slate-500">(optional, up to 10 files)</span></label>
            <input id="pp-ds" ref={dsRef} type="file" multiple className="text-sm" onChange={(e) => setDatasets([...(e.target.files || [])])} />
            <p className="mt-1 text-xs text-slate-500">CSV, XLSX, JSON, XML, TXT, ZIP, Parquet · up to 50 MB each. Once a mentor approves, your project and datasets are loaded onto the Project Shelf.</p>
            {errs.datasets && <p className="mt-1 text-xs text-red-600">{errs.datasets}</p>}</div>
          <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <label htmlFor="pp-sheet" className="label !mb-0">Data collection sheet (Excel){datasets.length > 0 ? ' *' : ''}</label>
              <button type="button" className="btn-secondary" onClick={() => proposalService.dataTemplate().catch((e) => setError(errorMessage(e, 'Download failed')))}><Download className="h-4 w-4" />Download Excel template</button>
            </div>
            <input id="pp-sheet" ref={sheetRef} type="file" accept=".xlsx" className="mt-2 text-sm" onChange={(e) => setSheet(e.target.files?.[0] || null)} />
            <p className="mt-1 text-xs text-slate-500">Describe each dataset (source, type, size, columns, collection method, licence, privacy…). Download the template, fill one row per dataset, and upload it here as .xlsx. Required when you upload datasets.</p>
            {errs.data_sheet && <p className="mt-1 text-xs text-red-600">{errs.data_sheet}</p>}
          </div>
          <div className="flex justify-end">
            <button className="btn-primary" disabled={locked || busy}><Upload className="h-4 w-4" />{busy ? 'Uploading…' : 'Submit for approval'}</button>
          </div>
        </fieldset>
      </form>

      <section className="card" aria-label="Submission history">
        <h3 className="mb-2 font-semibold text-slate-900">My submissions</h3>
        {info.proposals.length === 0 && <p className="text-sm text-slate-500">You have not submitted anything yet.</p>}
        <ul className="divide-y divide-slate-100">
          {info.proposals.map((p) => (
            <li key={p.id} className="flex items-start justify-between gap-3 py-3 text-sm">
              <div className="min-w-0">
                <div className="flex items-center gap-2"><span className="font-medium">{p.title}</span><StatusBadge tone={TONE[p.status]}>{p.status}</StatusBadge>{p.is_group && <StatusBadge tone="blue">Group</StatusBadge>}</div>
                {p.members?.length > 0 && <div className="mt-0.5 text-xs text-slate-600" aria-label="Group members">{p.members.map((m) => `${m.name}${m.role ? ` (${m.role})` : ''}`).join(', ')}</div>}
                <div className="text-xs text-slate-500">{p.file.name}{p.datasets.length ? ` · ${p.datasets.length} dataset(s)` : ''}{p.subdomain ? ` · ${p.subdomain.name}` : ''} · {new Date(p.submitted_at + 'Z').toLocaleDateString()}</div>
                {p.data_collection?.length > 0 && <div className="mt-1 text-xs text-slate-600">Data collection: {p.data_collection.map((r) => r.name).join(', ')}</div>}
                {p.shelf && <div className="mt-1 text-xs font-medium text-green-700">On the Project Shelf as {p.shelf.ps_code}</div>}
                {p.remarks && <div className="mt-1 text-slate-700"><span className="font-medium">Mentor remarks:</span> {p.remarks}</div>}
              </div>
              <button className="btn-secondary shrink-0" onClick={() => download(p)} aria-label={`Download ${p.file.name}`}><Download className="h-4 w-4" /></button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
