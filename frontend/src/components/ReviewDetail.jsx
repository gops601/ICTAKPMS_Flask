import StatusBadge from './StatusBadge'

const fmtNum = (n) => (Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/0+$/, '').replace(/\.$/, ''))
const toneFor = (pct) => (pct >= 75 ? 'green' : pct >= 50 ? 'orange' : 'red')
const FEEDBACK = [['remarks', 'Overall feedback'], ['strengths', 'Strengths'], ['improvements', 'Areas for improvement'], ['recommendations', 'Recommendations']]

/** Read-only evaluation: criteria, maximum, obtained, percentage and the mentor's written feedback. */
export default function ReviewDetail({ review }) {
  const s = review.summary
  return (
    <div className="space-y-4" aria-label={`Week ${review.week_no} evaluation`}>
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-slate-500">
        <span>{review.mentor ? `Reviewed by ${review.mentor}` : 'Not yet reviewed'}{review.review_date ? ` · ${review.review_date}` : ''}</span>
        <StatusBadge tone={toneFor(s.percentage)}>{fmtNum(s.total_obtained)} / {fmtNum(s.total_max)} · {fmtNum(s.percentage)}%</StatusBadge>
      </div>
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
          <tr><th className="py-2 pr-3 font-medium">Criterion</th><th className="px-3 py-2 font-medium">Max</th><th className="px-3 py-2 font-medium">Obtained</th><th className="px-3 py-2 font-medium">Remarks</th></tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {review.criteria.map((c) => (
            <tr key={c.id}>
              <td className="py-2 pr-3 font-medium">{c.name}</td>
              <td className="px-3 py-2">{fmtNum(c.max_marks)}</td>
              <td className="px-3 py-2">{c.marks_obtained == null ? '—' : fmtNum(c.marks_obtained)}</td>
              <td className="px-3 py-2 text-slate-600">{c.remarks || '—'}</td>
            </tr>
          ))}
          {review.criteria.length === 0 && <tr><td colSpan={4} className="py-4 text-center text-slate-500">No criteria defined yet.</td></tr>}
        </tbody>
        <tfoot className="border-t border-slate-300 font-semibold">
          <tr><td className="py-2 pr-3">Total</td><td className="px-3 py-2">{fmtNum(s.total_max)}</td><td className="px-3 py-2">{fmtNum(s.total_obtained)}</td><td className="px-3 py-2">{fmtNum(s.percentage)}%</td></tr>
        </tfoot>
      </table>
      {(review.student_remarks || []).some((s) => s.remarks) && (
        <section className="rounded-lg border border-emerald-100 bg-emerald-50/60 p-3" aria-label="Remarks for students">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-emerald-700">Remarks for each student</h4>
          <ul className="mt-1 space-y-1 text-sm text-slate-800">
            {review.student_remarks.filter((s) => s.remarks).map((s) => <li key={s.student_id}><span className="font-medium">{s.name}:</span> {s.remarks}</li>)}
          </ul>
        </section>
      )}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {FEEDBACK.filter(([k]) => review[k]).map(([k, label]) => (
          <section key={k} className="rounded-lg bg-slate-50 p-3" aria-label={label}>
            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</h4>
            <p className="mt-1 whitespace-pre-wrap text-sm text-slate-800">{review[k]}</p>
          </section>
        ))}
      </div>
    </div>
  )
}
