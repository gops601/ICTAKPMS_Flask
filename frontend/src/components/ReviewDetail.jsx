import StatusBadge from './StatusBadge'

const fmtNum = (n) => (Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/0+$/, '').replace(/\.$/, ''))
const toneFor = (pct) => (pct >= 75 ? 'green' : pct >= 50 ? 'orange' : 'red')
const FEEDBACK = [['remarks', 'Overall feedback'], ['strengths', 'Strengths'], ['improvements', 'Areas for improvement'], ['recommendations', 'Recommendations']]

/**
 * Read-only evaluation. Mentors, leads and admins see criteria, marks and the per-student evaluation;
 * students (review.summary === null) only see the mentor's remarks, never any score.
 */
export default function ReviewDetail({ review }) {
  const s = review.summary
  if (!s) return <StudentReviewDetail review={review} />
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
      {(review.student_remarks || []).some((x) => x.remarks || x.marks_obtained != null) && (
        <section className="rounded-lg border border-rose-100 bg-rose-50/60 p-3" aria-label="Individual evaluation">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-rose-700">Individual evaluation{review.individual_max_marks ? ` (out of ${fmtNum(review.individual_max_marks)})` : ''}</h4>
          <ul className="mt-1 space-y-1 text-sm text-slate-800">
            {review.student_remarks.filter((x) => x.remarks || x.marks_obtained != null).map((x) => (
              <li key={x.student_id}><span className="font-medium">{x.name}</span>{x.marks_obtained != null && <span className="ml-2 rounded bg-white px-1.5 py-0.5 text-xs font-semibold ring-1 ring-rose-200">{fmtNum(x.marks_obtained)}</span>}{x.remarks ? `: ${x.remarks}` : ''}</li>
            ))}
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

/** What a student sees: the mentor's written feedback only. No marks, totals or percentages. */
function StudentReviewDetail({ review }) {
  const mine = (review.student_remarks || []).find((x) => x.remarks)
  const criterionRemarks = (review.criteria || []).filter((c) => c.remarks)
  return (
    <div className="space-y-4" aria-label={`Week ${review.week_no} remarks`}>
      <div className="text-sm text-slate-500">{review.mentor ? `Reviewed by ${review.mentor}` : 'Reviewed'}{review.review_date ? ` · ${review.review_date}` : ''}</div>
      {mine && (
        <section className="rounded-lg border border-rose-100 bg-rose-50/60 p-3" aria-label="Your remarks">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-rose-700">Your individual remarks</h4>
          <p className="mt-1 whitespace-pre-wrap text-sm text-slate-800">{mine.remarks}</p>
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
      {criterionRemarks.length > 0 && (
        <section className="rounded-lg bg-slate-50 p-3" aria-label="Remarks by area">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Remarks by area</h4>
          <ul className="mt-1 space-y-1 text-sm text-slate-800">{criterionRemarks.map((c) => <li key={c.id}><span className="font-medium">{c.name}:</span> {c.remarks}</li>)}</ul>
        </section>
      )}
    </div>
  )
}
