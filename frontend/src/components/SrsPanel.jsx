import { useCallback, useEffect, useRef, useState } from 'react'
import { Download, FileUp, Lock, LockOpen } from 'lucide-react'
import { srsService } from '../services/adminService'
import { errorMessage, fieldErrors } from '../services/api'
import { useAuth } from '../context/AuthContext'
import Alert from './Alert'
import Spinner from './Spinner'
import StatusBadge from './StatusBadge'

const TONE = { not_submitted: 'grey', submitted: 'blue', under_review: 'orange', changes_requested: 'red', approved: 'green', rejected: 'red' }
const SUB_LABEL = { submitted: 'Submitted', under_review: 'Under Review', changes_requested: 'Changes Requested', approved: 'Approved', rejected: 'Rejected' }
const DECISION_LABEL = { under_review: 'Review started', approved: 'Approved', changes_requested: 'Changes requested', rejected: 'Rejected' }
const MAX_BYTES = 15 * 1024 * 1024
const fmt = (iso) => (iso ? new Date(`${iso}Z`).toLocaleString() : '—')
const fmtSize = (b) => (b >= 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`)

/** SRS status, submission (students) and review (mentors/admins). Everyone else gets a read-only view. */
export default function SrsPanel({ projectId }) {
  const { user } = useAuth()
  const isStudent = user.role === 'student'
  const canReview = user.role === 'mentor' || user.role === 'admin' || Boolean(user.is_mentor)
  const fileRef = useRef(null)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [file, setFile] = useState(null)
  const [description, setDescription] = useState('')
  const [remarks, setRemarks] = useState('')
  const [remarkError, setRemarkError] = useState('')

  const load = useCallback(() => srsService.get(projectId).then(setData).catch((e) => setError(errorMessage(e))), [projectId])
  useEffect(() => { load() }, [load])

  const onFile = (e) => {
    const f = e.target.files?.[0] || null
    setError('')
    if (f && f.size > MAX_BYTES) { setError('The file is too large (max 15 MB).'); e.target.value = ''; return setFile(null) }
    if (f && !/\.(pdf|docx)$/i.test(f.name)) { setError('Only PDF or DOCX files can be submitted.'); e.target.value = ''; return setFile(null) }
    setFile(f)
  }

  const submit = async (e) => {
    e.preventDefault()
    setError(''); setNotice('')
    if (!file) return setError('Choose a PDF or DOCX file first.')
    setBusy(true)
    try {
      setData(await srsService.submit(projectId, file, description))
      setFile(null); setDescription(''); if (fileRef.current) fileRef.current.value = ''
      setNotice('SRS submitted. Your mentor has been notified.')
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }

  const decide = async (decision) => {
    setError(''); setNotice(''); setRemarkError('')
    if ((decision === 'reject' || decision === 'request_changes') && remarks.trim().length < 3) {
      return setRemarkError('Comments are required when rejecting or requesting changes.')
    }
    setBusy(true)
    try {
      setData(await srsService.review(latest.id, decision, remarks))
      setRemarks(''); setNotice('Review saved.')
    } catch (err) { setError(errorMessage(err)); setRemarkError(fieldErrors(err).remarks || '') } finally { setBusy(false) }
  }

  const download = async (s) => {
    setError('')
    try { await srsService.download(s) } catch (e) { setError(errorMessage(e, 'Download failed')) }
  }

  if (!data) return error ? <Alert>{error}</Alert> : <Spinner />
  const latest = data.submissions[0]
  const reviewable = canReview && latest && ['submitted', 'under_review'].includes(latest.status)

  return (
    <div className="space-y-4">
      <div className="card flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-sm text-slate-500">SRS status – {data.title}</div>
          <div className="mt-1"><StatusBadge tone={TONE[data.status]}>{data.status_label}</StatusBadge></div>
        </div>
        <div className={`flex items-center gap-2 text-sm ${data.implementation_unlocked ? 'text-green-700' : 'text-slate-500'}`}>
          {data.implementation_unlocked ? <LockOpen className="h-4 w-4" /> : <Lock className="h-4 w-4" />}
          {data.implementation_unlocked ? 'Implementation unlocked' : 'Implementation locked until the SRS is approved'}
        </div>
      </div>

      <Alert>{error}</Alert>
      {notice && <Alert type="success">{notice}</Alert>}

      {isStudent && (
        <form onSubmit={submit} className="card space-y-3" aria-label="Submit SRS">
          <h2 className="font-semibold text-slate-900">{latest ? 'Submit a revised SRS' : 'Submit your SRS'}</h2>
          {!data.can_submit ? (
            <p className="text-sm text-slate-600">
              {data.status === 'approved' ? 'Your SRS has been approved.'
                : data.status === 'not_submitted' ? 'Start SRS preparation from My Project before submitting.'
                  : 'Your SRS is with your mentor for review. You can submit a revision if changes are requested.'}
            </p>
          ) : (
            <>
              {data.status === 'changes_requested' && <Alert type="warning">Your mentor asked for changes. Upload a revised document below.</Alert>}
              <div>
                <label htmlFor="srs-file" className="label">SRS document (PDF or DOCX, max 15 MB)</label>
                <input id="srs-file" ref={fileRef} type="file" accept=".pdf,.docx" className="text-sm" onChange={onFile} />
              </div>
              <div>
                <label htmlFor="srs-desc" className="label">Description (optional)</label>
                <textarea id="srs-desc" className="input" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
              </div>
              <button className="btn-primary" disabled={busy}><FileUp className="h-4 w-4" />{busy ? 'Uploading…' : 'Submit SRS'}</button>
            </>
          )}
        </form>
      )}

      {reviewable && (
        <div className="card space-y-3" aria-label="Review SRS">
          <h2 className="font-semibold text-slate-900">Review SRS v{latest.version}</h2>
          <div>
            <label htmlFor="srs-remarks" className="label">Comments <span className="font-normal text-slate-500">(required to reject or request changes)</span></label>
            <textarea id="srs-remarks" className="input" rows={3} value={remarks} onChange={(e) => setRemarks(e.target.value)} />
            {remarkError && <p className="mt-1 text-xs text-red-600">{remarkError}</p>}
          </div>
          <div className="flex flex-wrap gap-2">
            {latest.status === 'submitted' && <button className="btn-secondary" disabled={busy} onClick={() => decide('start_review')}>Start review</button>}
            <button className="btn bg-green-600 text-white hover:bg-green-700" disabled={busy} onClick={() => decide('approve')}>Approve</button>
            <button className="btn bg-orange-500 text-white hover:bg-orange-600" disabled={busy} onClick={() => decide('request_changes')}>Request changes</button>
            <button className="btn bg-red-600 text-white hover:bg-red-700" disabled={busy} onClick={() => decide('reject')}>Reject</button>
          </div>
        </div>
      )}

      <div className="card">
        <h2 className="mb-3 font-semibold text-slate-900">Submission history</h2>
        {data.submissions.length === 0 && <p className="text-sm text-slate-500">Nothing has been submitted yet.</p>}
        <ol className="space-y-4">
          {data.submissions.map((s) => (
            <li key={s.id} className="rounded-lg border border-slate-200 p-3" aria-label={`SRS version ${s.version}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="font-medium">Version {s.version}</span>
                  <StatusBadge tone={TONE[s.status]}>{SUB_LABEL[s.status]}</StatusBadge>
                </div>
                <button className="btn-secondary" onClick={() => download(s)} aria-label={`Download version ${s.version}`}>
                  <Download className="h-4 w-4" />{s.file.name} · {fmtSize(s.file.size_bytes)}
                </button>
              </div>
              <div className="mt-1 text-xs text-slate-500">Submitted {fmt(s.submitted_at)}</div>
              {s.description && <p className="mt-1 text-sm text-slate-700">{s.description}</p>}
              {s.history.length > 0 && (
                <ul className="mt-2 space-y-1 border-l-2 border-slate-200 pl-3">
                  {s.history.map((h) => (
                    <li key={h.id} className="text-sm">
                      <span className="font-medium">{DECISION_LABEL[h.decision]}</span>
                      <span className="text-slate-500"> · {h.reviewer || 'Reviewer'} · {fmt(h.at)}</span>
                      {h.remarks && <div className="text-slate-700">“{h.remarks}”</div>}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ol>
      </div>
    </div>
  )
}
