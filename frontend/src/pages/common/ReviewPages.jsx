import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ClipboardList, History, Plus, Trash2 } from 'lucide-react'
import { reviewService, templateService } from '../../services/adminService'
import { errorMessage, fieldErrors } from '../../services/api'
import { useList } from '../../hooks/useList'
import { useAuth } from '../../context/AuthContext'
import MyProjectGate from '../../components/MyProjectGate'
import ReviewDetail from '../../components/ReviewDetail'
import ReviewEditor from '../../components/ReviewEditor'
import PageHeader from '../../components/PageHeader'
import DataTable from '../../components/DataTable'
import Pagination from '../../components/Pagination'
import Modal from '../../components/Modal'
import ConfirmDialog from '../../components/ConfirmDialog'
import Alert from '../../components/Alert'
import Spinner from '../../components/Spinner'
import StatusBadge from '../../components/StatusBadge'
import BatchFilter from '../../components/BatchFilter'

const fmtNum = (n) => (Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/0+$/, '').replace(/\.$/, ''))
const TONE = { submitted: 'green', draft: 'orange', reopened: 'red', pending: 'grey' }
const fmtTime = (iso) => new Date(`${iso}Z`).toLocaleString()

// ---------------------------------------------------------------- single review
export function ReviewPage() {
  const { reviewId } = useParams()
  const { user } = useAuth()
  const [review, setReview] = useState(null)
  const [revisions, setRevisions] = useState([])
  const [error, setError] = useState('')
  const [reopening, setReopening] = useState(false)
  const [reason, setReason] = useState('')
  const [reopenError, setReopenError] = useState('')
  const [busy, setBusy] = useState(false)
  const canSeeHistory = user.role !== 'student'
  const isLead = user.role === 'domain_lead'

  const load = useCallback(async () => {
    try {
      const r = await reviewService.get(reviewId)
      setReview(r)
      if (canSeeHistory && r.visible) setRevisions(await reviewService.revisions(reviewId))
    } catch (e) { setError(errorMessage(e)) }
  }, [reviewId, canSeeHistory])
  useEffect(() => { load() }, [load])

  const reopen = async () => {
    setBusy(true); setReopenError('')
    try { setReview(await reviewService.reopen(reviewId, reason)); setReopening(false); setReason(''); setRevisions(await reviewService.revisions(reviewId)) }
    catch (e) { setReopenError(errorMessage(e)) } finally { setBusy(false) }
  }

  if (error && !review) return <Alert>{error}</Alert>
  if (!review) return <Spinner />
  const perms = review.permissions || {}

  return (
    <div className="max-w-5xl space-y-4">
      <PageHeader title={`Week ${review.week_no} evaluation`}
        subtitle={`Due ${review.due_date || '—'}${review.review_date ? ` · Review date ${review.review_date}` : ''}`}
        actions={<>
          <StatusBadge tone={TONE[review.status]}>{review.status_label}</StatusBadge>
          {perms.can_reopen && <button className="btn-secondary" onClick={() => { setReopenError(''); setReopening(true) }}>{isLead ? 'Revert to mentor' : 'Reopen to correct'}</button>}
          <Link to={`/reviews/project/${review.project_id}`} className="btn-secondary">All reviews</Link>
        </>} />
      {review.is_overdue && <Alert type="warning">This review is overdue.</Alert>}
      {review.date_request && (user.role === 'domain_lead' || user.role === 'admin') && (
        <Alert type="warning">
          {review.date_request.requested_by} asked to move this review from {review.date_request.old_date} to <b>{review.date_request.new_date}</b>: “{review.date_request.reason}”.{' '}
          <Link className="font-medium underline" to={`${user.role === 'admin' ? '/admin' : '/lead'}/date-requests`}>Review the request</Link>
        </Alert>
      )}
      {review.revert_note && perms.can_edit && (
        <Alert type="warning">
          Sent back for updating by {review.revert_note.by}{review.revert_note.by_role === 'domain_lead' ? ' (Domain Lead)' : ''}: “{review.revert_note.reason}”. Update the score and submit it again.
        </Alert>
      )}
      {(user.role === 'domain_lead' || user.role === 'admin') && review.visible && (
        <Alert type="info">Only the assigned mentor can give or change scores.{isLead ? ' If a score needs another look, revert it to the mentor with a reason.' : ''}</Alert>
      )}
      {!review.visible && <Alert type="info">This evaluation has not been published yet.</Alert>}
      {review.visible && perms.can_edit && <ReviewEditor key={review.version} review={review} onChange={setReview} />}
      {review.visible && !perms.can_edit && (
        <>
          {perms.reason && <Alert type="info">{perms.reason}</Alert>}
          <div className="card"><ReviewDetail review={review} /></div>
        </>
      )}

      {canSeeHistory && revisions.length > 0 && (
        <div className="card">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-slate-500"><History className="h-4 w-4" />Evaluation history</h2>
          <ul className="space-y-3">
            {revisions.map((r) => (
              <li key={r.id} className="rounded-lg border border-slate-200 p-3 text-sm" aria-label={`Revision ${r.id}`}>
                <div className="font-medium">Reopened by {r.changed_by} · {fmtTime(r.at)}</div>
                <div className="text-slate-600">Reason: “{r.reason}”</div>
                <div className="text-xs text-slate-500">Previous result: {fmtNum(r.snapshot.summary.total_obtained)} / {fmtNum(r.snapshot.summary.total_max)} ({fmtNum(r.snapshot.summary.percentage)}%)</div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {reopening && (
        <Modal title={isLead ? 'Revert score to mentor' : 'Reopen evaluation'} onClose={() => setReopening(false)}
          footer={<><button className="btn-secondary" onClick={() => setReopening(false)}>Cancel</button><button className="btn-primary" disabled={busy} onClick={reopen}>{busy ? 'Working…' : isLead ? 'Revert' : 'Reopen'}</button></>}>
          <div className="space-y-3">
            <Alert>{reopenError}</Alert>
            <p className="text-sm text-slate-600">
              {isLead ? 'The score goes back to the mentor, who is notified with your reason and can update it. ' : ''}
              The current evaluation is saved to the history and hidden from the student until it is resubmitted. This action is audited.
            </p>
            <label htmlFor="reopen-reason" className="label">Reason (required)</label>
            <textarea id="reopen-reason" className="input" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
          </div>
        </Modal>
      )}
    </div>
  )
}

// --------------------------------------------------------------- project reviews
function FinalPanel({ projectId, data, onDone }) {
  const [remarks, setRemarks] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const f = data.final_evaluation
  const sign = async (e) => {
    e.preventDefault(); setError('')
    if (remarks.trim().length < 3) return setError('Final evaluation remarks are required.')
    setBusy(true)
    try { await reviewService.signoff(projectId, remarks); onDone() } catch (err) { setError(errorMessage(err)); } finally { setBusy(false) }
  }
  return (
    <section className="card space-y-3" aria-label="Final evaluation">
      <h2 className="font-semibold text-slate-900">Final evaluation</h2>
      {f.signed_off ? (
        <div className="text-sm"><StatusBadge tone="green">Signed off</StatusBadge> <span className="text-slate-500">by {f.signed_by}</span>
          <p className="mt-2 whitespace-pre-wrap text-slate-800">{f.remarks}</p></div>
      ) : f.can_sign_off ? (
        <form onSubmit={sign} className="space-y-3">
          <Alert>{error}</Alert>
          <p className="text-sm text-slate-600">All four reviews are submitted. Sign off the final evaluation, then move the project to Completed from the project page.</p>
          <label htmlFor="final-remarks" className="label">Final remarks *</label>
          <textarea id="final-remarks" className="input" rows={3} value={remarks} onChange={(e) => setRemarks(e.target.value)} />
          <button className="btn-primary" disabled={busy}>{busy ? 'Signing off…' : 'Sign off final evaluation'}</button>
        </form>
      ) : (
        <p className="text-sm text-slate-500">
          {data.project.stage === 'final_evaluation' ? 'Waiting for the mentor to sign off.'
            : f.all_reviews_submitted ? 'All reviews are submitted. The project must be moved to the Final Evaluation stage before sign-off.'
              : 'Available once all four weekly reviews are submitted and the project reaches the Final Evaluation stage.'}
        </p>
      )}
    </section>
  )
}

export function ProjectReviewsView({ projectId }) {
  const { user } = useAuth()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const load = useCallback(() => reviewService.forProject(projectId).then(setData).catch((e) => setError(errorMessage(e))), [projectId])
  useEffect(() => { load() }, [load])

  if (!data) return error ? <Alert>{error}</Alert> : <Spinner />
  const o = data.overall
  const student = user.role === 'student'

  return (
    <div className="max-w-5xl space-y-4">
      <PageHeader title={student ? 'Weekly Reviews' : `Weekly reviews – ${data.project.title}`}
        subtitle={student ? data.project.title : data.project.stage_label}
        actions={!student && <Link to={`/projects/${projectId}`} className="btn-secondary">Project details</Link>} />
      <div className="card flex flex-wrap items-center gap-x-8 gap-y-2 text-sm" aria-label="Overall performance">
        <div><div className="text-slate-500">Reviews completed</div><div className="text-lg font-semibold">{o.reviews_submitted} / {o.reviews_total}</div></div>
        {!student && <>
          <div><div className="text-slate-500">Overall score</div><div className="text-lg font-semibold">{fmtNum(o.total_obtained)} / {fmtNum(o.total_max)}</div></div>
          <div><div className="text-slate-500">Overall percentage</div><div className="text-lg font-semibold">{fmtNum(o.percentage)}%</div></div>
          <div><div className="text-slate-500">Average of reviews</div><div className="text-lg font-semibold">{fmtNum(o.average_percentage)}%</div></div>
        </>}
        {student && <p className="text-slate-500">Your mentor's remarks appear below once each review is completed.</p>}
      </div>

      {data.reviews.map((r) => (
        <section key={r.id} className="card space-y-3" aria-label={`Week ${r.week_no}`}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <h2 className="font-semibold text-slate-900">Week {r.week_no}</h2>
              <StatusBadge tone={TONE[r.status]}>{r.status_label}</StatusBadge>
              {r.is_overdue && <StatusBadge tone="red">Overdue</StatusBadge>}
              <span className="text-xs text-slate-500">Due {r.due_date || '—'}</span>
              {r.review_date && r.status !== 'submitted' && <span className="text-xs font-medium text-brand">Scheduled {r.review_date}</span>}
            </div>
            {!student && <Link to={`/reviews/${r.id}`} className="btn-secondary">{r.permissions.can_edit ? 'Evaluate' : 'Open'}</Link>}
          </div>
          {r.visible && r.status === 'submitted' && student && <ReviewDetail review={r} />}
          {r.visible && r.status !== 'submitted' && !student && (
            <p className="text-sm text-slate-600">{r.summary.scored_count}/{r.summary.criteria_count} criteria scored · {fmtNum(r.summary.percentage)}% so far</p>
          )}
          {r.visible && r.status === 'submitted' && !student && (
            <p className="text-sm text-slate-600">{fmtNum(r.summary.total_obtained)} / {fmtNum(r.summary.total_max)} ({fmtNum(r.summary.percentage)}%)</p>
          )}
          {!r.visible && <p className="text-sm text-slate-500">{r.status_label === 'Under revision' ? 'Your mentor is correcting this evaluation.' : 'Not evaluated yet.'}</p>}
        </section>
      ))}
      <FinalPanel projectId={projectId} data={data} onDone={load} />
    </div>
  )
}

export function ProjectReviewsPage() {
  const { projectId } = useParams()
  return <ProjectReviewsView key={projectId} projectId={projectId} />
}

export function StudentReviewsPage() {
  return <MyProjectGate title="Weekly Reviews">{(p) => <ProjectReviewsView projectId={p.id} />}</MyProjectGate>
}

// -------------------------------------------------------------------------- queue
export function EvaluationQueuePage() {
  const { user } = useAuth()
  const [page, setPage] = useState(1)
  const [week, setWeek] = useState('')
  const [overdue, setOverdue] = useState(false)
  const [batchId, setBatchId] = useState('')
  const { items, meta, loading, error } = useList(reviewService.queue, { page, batch_id: batchId || undefined, week: week || undefined, overdue: overdue ? 1 : undefined })
  const evaluator = user.role === 'mentor'
  return (
    <div>
      <PageHeader title={evaluator ? 'Weekly Evaluations' : 'Review Monitoring'} subtitle="Reviews still to be completed, soonest due first." />
      <div className="card">
        <div className="mb-4 flex flex-wrap items-center gap-4">
          <BatchFilter value={batchId} onChange={(v) => { setBatchId(v); setPage(1) }} />
          <select className="input !w-auto" aria-label="Filter by week" value={week} onChange={(e) => { setWeek(e.target.value); setPage(1) }}>
            <option value="">All weeks</option>{[1, 2, 3, 4].map((w) => <option key={w} value={w}>Week {w}</option>)}
          </select>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={overdue} onChange={(e) => { setOverdue(e.target.checked); setPage(1) }} />Overdue only</label>
        </div>
        <Alert>{error}</Alert>
        <DataTable loading={loading} rows={items} rowKey="review_id" empty="No pending evaluations." columns={[
          { key: 'project', header: 'Project', render: (r) => <div><div className="font-medium">{r.project.title}</div><div className="text-xs text-slate-500">Batch {r.project.batch} · {r.project.students.join(', ')}</div></div> },
          { key: 'week', header: 'Week', render: (r) => `Week ${r.week_no}` },
          { key: 'due', header: 'Due', render: (r) => <span className={r.is_overdue ? 'font-medium text-red-600' : ''}>{r.due_date}{r.is_overdue ? ' · overdue' : ''}</span> },
          { key: 'status', header: 'Status', render: (r) => <StatusBadge tone={TONE[r.status]}>{r.status_label}</StatusBadge> },
          { key: 'actions', header: '', render: (r) => <Link className="btn-secondary" to={`/reviews/${r.review_id}`}><ClipboardList className="h-4 w-4" />{evaluator ? 'Evaluate' : 'View'}</Link> },
        ]} />
        <Pagination meta={meta} onPage={setPage} />
      </div>
    </div>
  )
}

// ----------------------------------------------------------------- templates page
function TemplateModal({ template, onClose, onSaved }) {
  const [name, setName] = useState(template?.name || '')
  const [week, setWeek] = useState(template?.week_no ? String(template.week_no) : '')
  const [rows, setRows] = useState(template ? template.criteria.map((c, i) => ({ k: i, name: c.name, max_marks: String(c.max_marks) })) : [{ k: 0, name: '', max_marks: '' }])
  const [error, setError] = useState('')
  const [errs, setErrs] = useState({})
  const [busy, setBusy] = useState(false)

  const save = async (e) => {
    e.preventDefault(); setBusy(true); setError(''); setErrs({})
    const body = { name, week_no: week ? Number(week) : null, criteria: rows.map((r) => ({ name: r.name, max_marks: r.max_marks })) }
    try { template ? await templateService.update(template.id, body) : await templateService.create(body); onSaved() }
    catch (err) { setError(errorMessage(err)); setErrs(fieldErrors(err)) } finally { setBusy(false) }
  }
  const total = rows.reduce((s, r) => s + (Number(r.max_marks) || 0), 0)

  return (
    <Modal title={template ? 'Edit template' : 'New template'} onClose={onClose} wide>
      <form onSubmit={save} className="space-y-3">
        <Alert>{error}</Alert>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="sm:col-span-2"><label htmlFor="tp-name" className="label">Name *</label><input id="tp-name" className="input" required value={name} onChange={(e) => setName(e.target.value)} /></div>
          <div><label htmlFor="tp-week" className="label">Suggested for</label>
            <select id="tp-week" className="input" value={week} onChange={(e) => setWeek(e.target.value)}><option value="">Any week</option>{[1, 2, 3, 4].map((w) => <option key={w} value={w}>Week {w}</option>)}</select></div>
        </div>
        <div className="space-y-2">
          {rows.map((r, i) => (
            <div key={r.k} className="grid grid-cols-12 gap-2">
              <div className="col-span-8"><input className="input" aria-label={`Template criterion ${i + 1} name`} placeholder="Criterion" value={r.name} onChange={(e) => setRows(rows.map((x) => (x.k === r.k ? { ...x, name: e.target.value } : x)))} />{errs[`criteria.${i}.name`] && <p className="text-xs text-red-600">{errs[`criteria.${i}.name`]}</p>}</div>
              <div className="col-span-3"><input className="input" type="number" min="0" step="0.01" aria-label={`Template criterion ${i + 1} marks`} placeholder="Max" value={r.max_marks} onChange={(e) => setRows(rows.map((x) => (x.k === r.k ? { ...x, max_marks: e.target.value } : x)))} />{errs[`criteria.${i}.max_marks`] && <p className="text-xs text-red-600">{errs[`criteria.${i}.max_marks`]}</p>}</div>
              <div className="col-span-1"><button type="button" className="btn-secondary" aria-label={`Remove template criterion ${i + 1}`} onClick={() => setRows(rows.filter((x) => x.k !== r.k))}><Trash2 className="h-4 w-4" /></button></div>
            </div>
          ))}
        </div>
        <div className="flex items-center justify-between">
          <button type="button" className="btn-secondary" onClick={() => setRows([...rows, { k: Math.max(0, ...rows.map((r) => r.k)) + 1, name: '', max_marks: '' }])}><Plus className="h-4 w-4" />Add criterion</button>
          <span className="text-sm text-slate-600">Total marks: <b>{fmtNum(total)}</b></span>
        </div>
        <div className="flex justify-end gap-2"><button type="button" className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Save template'}</button></div>
      </form>
    </Modal>
  )
}

export function TemplatesPage() {
  const [templates, setTemplates] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [editing, setEditing] = useState(null) // 'new' | template
  const [deleting, setDeleting] = useState(null)
  const [busy, setBusy] = useState(false)
  const load = useCallback(() => templateService.list().then(setTemplates).catch((e) => setError(errorMessage(e))), [])
  useEffect(() => { load() }, [load])

  const samples = async () => {
    setError(''); setNotice('')
    try { const added = await templateService.samples(); setNotice(added.length ? `${added.length} sample template(s) added. Edit or delete them freely.` : 'Sample templates are already in your list.'); load() }
    catch (e) { setError(errorMessage(e)) }
  }
  const remove = async () => {
    setBusy(true)
    try { await templateService.remove(deleting.id); setDeleting(null); load() } catch (e) { setError(errorMessage(e)); setDeleting(null) } finally { setBusy(false) }
  }

  return (
    <div>
      <PageHeader title="Evaluation Templates" subtitle="Reusable criteria sets. You can still add or change criteria on each review."
        actions={<>
          <button className="btn-secondary" onClick={samples}>Add sample templates</button>
          <button className="btn-primary" onClick={() => setEditing('new')}><Plus className="h-4 w-4" />New template</button>
        </>} />
      <Alert>{error}</Alert>
      {notice && <Alert type="success">{notice}</Alert>}
      <div className="card mt-3">
        {templates === null ? <Spinner /> : (
          <DataTable rows={templates} empty="No templates yet. Create one or add the sample templates." columns={[
            { key: 'name', header: 'Name' },
            { key: 'week', header: 'Suggested for', render: (t) => (t.week_no ? `Week ${t.week_no}` : 'Any week') },
            { key: 'criteria', header: 'Criteria', render: (t) => t.criteria.map((c) => `${c.name} (${fmtNum(c.max_marks)})`).join(', ') },
            { key: 'total', header: 'Total', render: (t) => fmtNum(t.total_marks) },
            { key: 'actions', header: '', render: (t) => (
              <div className="flex gap-2"><button className="btn-secondary" onClick={() => setEditing(t)}>Edit</button>
                <button className="btn-secondary" aria-label={`Delete ${t.name}`} onClick={() => setDeleting(t)}><Trash2 className="h-4 w-4" /></button></div>
            ) },
          ]} />
        )}
      </div>
      {editing && <TemplateModal template={editing === 'new' ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load() }} />}
      {deleting && <ConfirmDialog danger confirmLabel="Delete" busy={busy} message={`Delete the template “${deleting.name}”? Reviews already using its criteria are not affected.`} onConfirm={remove} onCancel={() => setDeleting(null)} />}
    </div>
  )
}
