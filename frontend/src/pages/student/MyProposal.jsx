import { useCallback, useEffect, useRef, useState } from 'react'
import { Download, Upload } from 'lucide-react'
import { proposalService } from '../../services/adminService'
import { errorMessage, fieldErrors } from '../../services/api'
import PageHeader from '../../components/PageHeader'
import StatusBadge from '../../components/StatusBadge'
import Alert from '../../components/Alert'
import Spinner from '../../components/Spinner'

const TONE = { pending: 'orange', approved: 'green', rejected: 'red', withdrawn: 'grey' }

/** Students propose their own detailed problem statement; a mentor must approve it. Locked once a project is allocated. */
export default function MyProposal() {
  const fileRef = useRef(null)
  const [info, setInfo] = useState(null)
  const [form, setForm] = useState({ title: '', summary: '' })
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [errs, setErrs] = useState({})
  const [done, setDone] = useState(false)

  const load = useCallback(() => proposalService.mine().then(setInfo).catch((e) => setError(errorMessage(e))), [])
  useEffect(() => { load() }, [load])

  const submit = async (e) => {
    e.preventDefault()
    if (!file) return setError('Choose the detailed problem statement file first.')
    setBusy(true); setError(''); setErrs({}); setDone(false)
    try {
      await proposalService.submit(form.title, form.summary, file)
      setForm({ title: '', summary: '' }); setFile(null); setDone(true)
      if (fileRef.current) fileRef.current.value = ''
      await load()
    } catch (err) { setError(errorMessage(err)); setErrs(fieldErrors(err)) } finally { setBusy(false) }
  }
  const download = async (p) => { try { await proposalService.download(p) } catch (e) { setError(errorMessage(e, 'Download failed')) } }

  if (!info) return error ? <Alert>{error}</Alert> : <Spinner />
  const locked = !info.can_upload

  return (
    <div className="max-w-3xl space-y-4">
      <PageHeader title="My Problem Statement" subtitle="Propose your own detailed problem statement. Your mentor must approve it." />
      <Alert>{error}</Alert>
      {done && <Alert type="success">Submitted. Your mentor has been notified.</Alert>}
      {locked && <Alert type={info.has_project ? 'warning' : 'info'}>{info.blocked_reason}</Alert>}

      <form onSubmit={submit} className="card space-y-3" aria-label="Upload problem statement">
        <fieldset disabled={locked || busy} className="space-y-3 disabled:opacity-60">
          <div><label htmlFor="pp-title" className="label">Title *</label>
            <input id="pp-title" className="input" required maxLength={255} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
            {errs.title && <p className="mt-1 text-xs text-red-600">{errs.title}</p>}</div>
          <div><label htmlFor="pp-sum" className="label">Short summary</label>
            <textarea id="pp-sum" className="input min-h-[80px]" value={form.summary} onChange={(e) => setForm({ ...form, summary: e.target.value })} /></div>
          <div><label htmlFor="pp-file" className="label">Detailed problem statement *</label>
            <input id="pp-file" ref={fileRef} type="file" className="text-sm" onChange={(e) => setFile(e.target.files?.[0] || null)} />
            <p className="mt-1 text-xs text-slate-500">PDF, Word, PowerPoint, Excel, images or text · up to 25 MB.</p></div>
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
                <div className="flex items-center gap-2"><span className="font-medium">{p.title}</span><StatusBadge tone={TONE[p.status]}>{p.status}</StatusBadge></div>
                <div className="text-xs text-slate-500">{p.file.name} · {new Date(p.submitted_at + 'Z').toLocaleDateString()}</div>
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
