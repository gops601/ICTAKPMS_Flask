import { useEffect, useMemo, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { reviewDateService, reviewService, templateService } from '../services/adminService'
import { errorMessage, fieldErrors } from '../services/api'
import Alert from './Alert'
import ConfirmDialog from './ConfirmDialog'
import Modal from './Modal'

let keySeq = 0
const newRow = (c = {}) => ({
  key: `r${++keySeq}`, id: c.id ?? null, name: c.name ?? '', max_marks: c.max_marks ?? '', marks_obtained: c.marks_obtained ?? '', remarks: c.remarks ?? '',
})
const num = (v) => (v === '' || v === null || v === undefined ? null : Number(v))
const fmt = (n) => (Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/0+$/, '').replace(/\.$/, ''))

/** Live totals that mirror the server: unscored criteria count as 0 but still add to the maximum. */
export function computeTotals(rows) {
  const max = rows.reduce((s, r) => s + (num(r.max_marks) || 0), 0)
  const got = rows.reduce((s, r) => s + (num(r.marks_obtained) || 0), 0)
  return { max, got, pct: max ? Math.round((got * 10000) / max) / 100 : 0 }
}

/** Mentor's evaluation form: dynamic criteria, scores, feedback. `review.permissions.can_edit` must be true. */
export default function ReviewEditor({ review, onChange }) {
  const [rows, setRows] = useState(() => review.criteria.map(newRow))
  const [fb, setFb] = useState({ remarks: review.remarks || '', strengths: review.strengths || '', improvements: review.improvements || '', recommendations: review.recommendations || '', review_date: review.review_date || '' })
  const [students, setStudents] = useState(() => (review.student_remarks || []).map((s) => ({ ...s, marks_obtained: s.marks_obtained ?? '' })))
  const [indMax, setIndMax] = useState(review.individual_max_marks ?? 10)
  const [templates, setTemplates] = useState([])
  const [tplId, setTplId] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [errs, setErrs] = useState({})
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState(null) // 'submit' | 'template'
  const dateLocked = Boolean(review.review_date)          // a saved date can only move through an approved request
  const [dateDialog, setDateDialog] = useState(false)
  const [dateForm, setDateForm] = useState({ new_date: '', reason: '' })
  const [dateError, setDateError] = useState('')

  useEffect(() => { templateService.list({ week: review.week_no }).then(setTemplates).catch(() => {}) }, [review.week_no])
  const totals = useMemo(() => computeTotals(rows), [rows])

  const setRow = (key, patch) => setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)))
  const payload = () => ({
    criteria: rows.map((r) => ({ id: r.id, name: r.name, max_marks: r.max_marks, marks_obtained: r.marks_obtained === '' ? null : r.marks_obtained, remarks: r.remarks })),
    ...fb, review_date: fb.review_date || null, version: review.version,
    individual_max_marks: indMax,
    student_remarks: students.map((s) => ({ student_id: s.student_id, remarks: s.remarks, marks_obtained: s.marks_obtained === '' ? null : s.marks_obtained })),
  })

  const localCheck = () => {
    const e = {}
    const seen = new Set()
    rows.forEach((r, i) => {
      const name = r.name.trim().toLowerCase()
      if (!name) e[`criteria.${i}.name`] = 'Name is required'
      else if (seen.has(name)) e[`criteria.${i}.name`] = 'Duplicate criterion'
      seen.add(name)
      if (!(num(r.max_marks) > 0)) e[`criteria.${i}.max_marks`] = 'Max marks must be greater than 0'
      if (num(r.marks_obtained) !== null && (num(r.marks_obtained) < 0 || num(r.marks_obtained) > num(r.max_marks))) e[`criteria.${i}.marks_obtained`] = 'Between 0 and the maximum'
    })
    return e
  }

  const run = async (fn, okMsg) => {
    setError(''); setNotice('')
    const local = localCheck()
    setErrs(local)
    if (Object.keys(local).length) return setError('Please fix the highlighted criteria.')
    setBusy(true)
    try {
      const updated = await fn()
      setNotice(okMsg)
      onChange(updated)
    } catch (e) { setError(errorMessage(e)); setErrs(fieldErrors(e)) } finally { setBusy(false); setConfirm(null) }
  }

  const sendDateRequest = async () => {
    setDateError('')
    if (!dateForm.new_date) return setDateError('Choose the new date.')
    if (dateForm.reason.trim().length < 5) return setDateError('Give a reason (at least 5 characters).')
    setBusy(true)
    try {
      await reviewDateService.create(review.id, dateForm.new_date, dateForm.reason)
      setDateDialog(false); setDateForm({ new_date: '', reason: '' }); setNotice('Request sent to your Domain Lead.')
      onChange(await reviewService.get(review.id))
    } catch (err) { setDateError(errorMessage(err)) } finally { setBusy(false) }
  }
  const withdrawDateRequest = async () => {
    setBusy(true); setError('')
    try { await reviewDateService.cancel(review.date_request.id); setNotice('Request withdrawn.'); onChange(await reviewService.get(review.id)) }
    catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }

  const save = () => run(() => reviewService.save(review.id, payload()), 'Draft saved.')
  const submit = () => run(() => reviewService.submit(review.id, payload()), 'Evaluation submitted.')

  const applyTemplate = async () => {
    setBusy(true); setError('')
    try {
      const updated = await reviewService.applyTemplate(review.id, Number(tplId))
      setRows(updated.criteria.map(newRow)); setNotice('Template applied.'); onChange(updated)
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false); setConfirm(null) }
  }
  const startTemplate = () => (rows.some((r) => r.marks_obtained !== '' || r.id) ? setConfirm('template') : applyTemplate())

  const e = (k) => errs[k] && <p className="mt-0.5 text-xs text-red-600">{errs[k]}</p>
  const cell = 'input !py-1.5'

  return (
    <div className="space-y-4">
      <Alert>{error}</Alert>
      {notice && <Alert type="success">{notice}</Alert>}

      <div className="card space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 className="font-semibold text-slate-900">Evaluation criteria & marks</h2>
          {templates.length > 0 && (
            <div className="flex items-end gap-2">
              <div>
                <label htmlFor="tpl" className="label">Start from a template</label>
                <select id="tpl" className="input !py-1.5" value={tplId} onChange={(ev) => setTplId(ev.target.value)}>
                  <option value="">Choose…</option>{templates.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.total_marks} marks)</option>)}
                </select>
              </div>
              <button type="button" className="btn-secondary" disabled={!tplId || busy} onClick={startTemplate}>Apply</button>
            </div>
          )}
        </div>

        <div className="space-y-2">
          <div className="hidden grid-cols-12 gap-2 text-xs font-medium uppercase text-slate-500 sm:grid">
            <div className="col-span-4">Criterion</div><div className="col-span-2">Max marks</div><div className="col-span-2">Marks obtained</div><div className="col-span-3">Remarks</div><div />
          </div>
          {rows.map((r, i) => (
            <div key={r.key} className="grid grid-cols-1 items-start gap-2 sm:grid-cols-12" role="group" aria-label={`Criterion ${i + 1}`}>
              <div className="sm:col-span-4"><input className={cell} aria-label={`Criterion ${i + 1} name`} placeholder="e.g. System Design" value={r.name} onChange={(ev) => setRow(r.key, { name: ev.target.value })} />{e(`criteria.${i}.name`)}</div>
              <div className="sm:col-span-2"><input className={cell} type="number" min="0" step="0.01" aria-label={`Criterion ${i + 1} maximum marks`} value={r.max_marks} onChange={(ev) => setRow(r.key, { max_marks: ev.target.value })} />{e(`criteria.${i}.max_marks`)}</div>
              <div className="sm:col-span-2"><input className={cell} type="number" min="0" step="0.01" aria-label={`Criterion ${i + 1} marks obtained`} value={r.marks_obtained} onChange={(ev) => setRow(r.key, { marks_obtained: ev.target.value })} />{e(`criteria.${i}.marks_obtained`)}</div>
              <div className="sm:col-span-3"><input className={cell} aria-label={`Criterion ${i + 1} remarks`} placeholder="Optional" value={r.remarks} onChange={(ev) => setRow(r.key, { remarks: ev.target.value })} /></div>
              <div className="sm:col-span-1"><button type="button" className="btn-secondary" aria-label={`Remove criterion ${i + 1}`} onClick={() => setRows((rs) => rs.filter((x) => x.key !== r.key))}><Trash2 className="h-4 w-4" /></button></div>
            </div>
          ))}
          {rows.length === 0 && <p className="text-sm text-slate-500">No criteria yet. Add your own, or start from a template.</p>}
        </div>
        <button type="button" className="btn-secondary" onClick={() => setRows((rs) => [...rs, newRow()])}><Plus className="h-4 w-4" />Add criterion</button>

        <div className="flex flex-wrap gap-6 rounded-lg bg-slate-50 p-3 text-sm" aria-label="Totals">
          <span>Total obtained: <b>{fmt(totals.got)}</b></span><span>Maximum: <b>{fmt(totals.max)}</b></span><span>Percentage: <b>{fmt(totals.pct)}%</b></span>
        </div>
      </div>

      <div className="card space-y-3">
        <h2 className="font-semibold text-slate-900">Feedback</h2>
        <div><label htmlFor="fb-remarks" className="label">Overall feedback *</label><textarea id="fb-remarks" className="input" rows={3} value={fb.remarks} onChange={(ev) => setFb({ ...fb, remarks: ev.target.value })} />{e('remarks')}</div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div><label htmlFor="fb-str" className="label">Strengths</label><textarea id="fb-str" className="input" rows={3} value={fb.strengths} onChange={(ev) => setFb({ ...fb, strengths: ev.target.value })} /></div>
          <div><label htmlFor="fb-imp" className="label">Areas for improvement</label><textarea id="fb-imp" className="input" rows={3} value={fb.improvements} onChange={(ev) => setFb({ ...fb, improvements: ev.target.value })} /></div>
          <div><label htmlFor="fb-rec" className="label">Recommendations</label><textarea id="fb-rec" className="input" rows={3} value={fb.recommendations} onChange={(ev) => setFb({ ...fb, recommendations: ev.target.value })} /></div>
        </div>
        <div className="max-w-md space-y-2" aria-label="Review date">
          <label htmlFor="fb-date" className="label">Review date</label>
          <input id="fb-date" type="date" className="input" value={fb.review_date} disabled={dateLocked}
            onChange={(ev) => setFb({ ...fb, review_date: ev.target.value })} />
          {e('review_date')}
          {!dateLocked && <p className="text-xs text-slate-500">Set the date of this review. Once it is saved, changing it needs your Domain Lead&apos;s approval.</p>}
          {dateLocked && !review.date_request && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-slate-500">Scheduled – changes need your Domain Lead&apos;s approval.</span>
              {review.permissions?.can_request_date_change && <button type="button" className="btn-secondary" onClick={() => { setDateError(''); setDateDialog(true) }}>Request date change</button>}
            </div>
          )}
          {review.date_request && (
            <Alert type="warning">
              Waiting for Domain Lead approval: move to <b>{review.date_request.new_date}</b> – “{review.date_request.reason}”.
              <div className="mt-2"><button type="button" className="btn-secondary" disabled={busy} onClick={withdrawDateRequest}>Withdraw request</button></div>
            </Alert>
          )}
        </div>
      </div>

      {students.length > 0 && (
        <div className="card space-y-3" aria-label="Remarks for each student">
          <div>
            <h2 className="font-semibold text-slate-900">Individual evaluation</h2>
            <p className="text-xs text-slate-500">
              {students.length > 1 ? 'Required for every team member: individual marks and a remark. ' : 'Optional for a solo project. '}
              Students only see their own remark, never any marks.
            </p>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <label htmlFor="ind-max" className="text-slate-600">Individual marks are out of</label>
            <input id="ind-max" type="number" min="1" className="input !w-24" value={indMax} onChange={(ev) => setIndMax(ev.target.value)} />
          </div>
          {students.map((s) => (
            <div key={s.student_id}>
              <label htmlFor={`sr-${s.student_id}`} className="label">{s.name} <span className="font-normal text-slate-500">· {s.registration_no}</span></label>
              <div className="flex gap-2">
                <input type="number" min="0" step="0.5" aria-label={`Individual marks for ${s.name}`} placeholder="Marks" className="input !w-24 shrink-0" value={s.marks_obtained}
                  onChange={(ev) => setStudents((list) => list.map((x) => (x.student_id === s.student_id ? { ...x, marks_obtained: ev.target.value } : x)))} />
                <textarea id={`sr-${s.student_id}`} aria-label={`Remarks for ${s.name}`} className="input" rows={2} value={s.remarks}
                  onChange={(ev) => setStudents((list) => list.map((x) => (x.student_id === s.student_id ? { ...x, remarks: ev.target.value } : x)))} />
              </div>
              {errs[`student_remarks.${students.indexOf(s)}`] && <p className="mt-0.5 text-xs text-red-600">{errs[`student_remarks.${students.indexOf(s)}`]}</p>}
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap justify-end gap-2">
        <button className="btn-secondary" disabled={busy} onClick={save}>Save draft</button>
        <button className="btn-primary" disabled={busy} onClick={() => { setError(''); const l = localCheck(); setErrs(l); if (Object.keys(l).length) return setError('Please fix the highlighted criteria.'); setConfirm('submit') }}>Submit evaluation</button>
      </div>

      {dateDialog && (
        <Modal title="Request a review date change" onClose={() => setDateDialog(false)}
          footer={<><button className="btn-secondary" onClick={() => setDateDialog(false)}>Cancel</button><button className="btn-primary" disabled={busy} onClick={sendDateRequest}>{busy ? 'Sending…' : 'Send for approval'}</button></>}>
          <div className="space-y-3">
            <Alert>{dateError}</Alert>
            <p className="text-sm text-slate-600">Current date: <b>{review.review_date}</b>. Your Domain Lead will approve or reject the change; nothing moves until then.</p>
            <div><label htmlFor="dr-date" className="label">New review date</label>
              <input id="dr-date" type="date" className="input" min={new Date().toISOString().slice(0, 10)} value={dateForm.new_date} onChange={(ev) => setDateForm({ ...dateForm, new_date: ev.target.value })} /></div>
            <div><label htmlFor="dr-reason" className="label">Reason</label>
              <textarea id="dr-reason" className="input" rows={3} value={dateForm.reason} onChange={(ev) => setDateForm({ ...dateForm, reason: ev.target.value })} /></div>
          </div>
        </Modal>
      )}
      {confirm === 'submit' && (
        <ConfirmDialog title="Submit evaluation?" confirmLabel="Submit" busy={busy} onCancel={() => setConfirm(null)} onConfirm={submit}
          message={`The student will see ${fmt(totals.got)}/${fmt(totals.max)} (${fmt(totals.pct)}%) and your feedback. After submission criteria and marks are locked; changing them later needs a reason and is audited.`} />
      )}
      {confirm === 'template' && (
        <ConfirmDialog title="Replace criteria?" confirmLabel="Replace" danger busy={busy} onCancel={() => setConfirm(null)} onConfirm={applyTemplate}
          message="Applying a template replaces the current criteria and clears the marks you entered." />
      )}
    </div>
  )
}
