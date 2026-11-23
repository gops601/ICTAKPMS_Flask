import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { dashboardService } from '../../services/adminService'
import BatchFilter from '../../components/BatchFilter'
import WelcomeBanner from '../../components/WelcomeBanner'
import { errorMessage } from '../../services/api'
import { Bars, ChartCard, COLORS, Donut, StatCard, StatGrid, statusSlices } from '../../components/charts'
import { ProgressBar, StageBadge } from '../../components/ProjectBadges'
import StatusBadge from '../../components/StatusBadge'
import PageHeader from '../../components/PageHeader'
import Alert from '../../components/Alert'
import Spinner from '../../components/Spinner'

const fmtDate = (d) => (d ? new Date(`${d}T00:00:00`).toLocaleDateString() : '—')

function useDashboard(batchId) {
  const [state, setState] = useState({ data: null, error: '' })
  useEffect(() => {
    let live = true
    dashboardService.get(batchId ? { batch_id: batchId } : undefined)
      .then((data) => live && setState({ data, error: '' })).catch((e) => live && setState({ data: null, error: errorMessage(e) }))
    return () => { live = false }
  }, [batchId])
  return state
}

/** `filterable` dashboards (admin, domain lead, mentor) get a batch selector; the API enforces what each role may pick. */
function Shell({ title, subtitle, filterable = false, children }) {
  const [batchId, setBatchId] = useState('')
  const { data, error } = useDashboard(batchId)
  // The header (and its batch selector) stays mounted across loads so the selection and option list persist.
  return (
    <div className="space-y-5">
      <WelcomeBanner />
      <PageHeader title={title} subtitle={batchId ? `${subtitle} (filtered to the selected batch)` : subtitle}
        actions={filterable ? <BatchFilter value={batchId} onChange={setBatchId} /> : null} />
      {error ? <Alert>{error}</Alert> : !data ? <Spinner /> : children(data)}
    </div>
  )
}

const stageTable = { columns: [{ key: 'label', label: 'Stage' }, { key: 'count', label: 'Projects' }] }
const noneIn = (rows, key = 'count') => rows.every((r) => !r[key])

function StageChart({ rows }) {
  return (
    <ChartCard title="Project stage distribution" subtitle="Where every project currently is" table={{ ...stageTable, rows }} empty={noneIn(rows)} height={300}
      summary={`Projects per stage: ${rows.filter((r) => r.count).map((r) => `${r.label} ${r.count}`).join(', ')}`}>
      <Bars data={rows} categoryKey="label" series={[{ key: 'count', label: 'Projects' }]} horizontal />
    </ChartCard>
  )
}

function StatusChart({ split }) {
  const total = split.completed + split.ongoing + split.delayed
  return (
    <ChartCard title="Completed vs ongoing vs delayed" empty={total === 0} height={220}
      table={{ columns: [{ key: 'label', label: 'Status' }, { key: 'value', label: 'Projects' }], rows: statusSlices(split) }}
      summary={`${split.completed} completed, ${split.ongoing} ongoing, ${split.delayed} delayed`}>
      <Donut slices={statusSlices(split)} />
    </ChartCard>
  )
}

const WEEK_SERIES = [{ key: 'submitted', label: 'Submitted' }, { key: 'in_progress', label: 'In progress' }, { key: 'pending', label: 'Pending' }]
const WEEK_TABLE = { columns: [{ key: 'week', label: 'Week' }, { key: 'submitted', label: 'Submitted' }, { key: 'in_progress', label: 'In progress' }, { key: 'pending', label: 'Pending' }] }

function WeeklyStatusChart({ rows, title = 'Weekly evaluation status' }) {
  return (
    <ChartCard title={title} table={{ ...WEEK_TABLE, rows }} empty={rows.every((r) => !r.submitted && !r.in_progress && !r.pending)}>
      <Bars data={rows} categoryKey="week" series={WEEK_SERIES} stacked />
    </ChartCard>
  )
}

function BatchProgress({ rows }) {
  return (
    <ChartCard title="Batch-wise progress" subtitle="Average project progress per batch (%)" empty={rows.length === 0} height={Math.max(220, rows.length * 34)}
      table={{ columns: [{ key: 'batch', label: 'Batch' }, { key: 'average_progress', label: 'Avg progress %' }, { key: 'projects', label: 'Projects' }], rows }}>
      <Bars data={rows} categoryKey="batch" series={[{ key: 'average_progress', label: 'Average progress' }]} horizontal domain={[0, 100]} unit="%" />
    </ChartCard>
  )
}

function ScrumSummary({ scrum }) {
  const slices = [
    { label: 'Completed', value: scrum.completed, color: COLORS.good, icon: null },
    { label: 'Open', value: scrum.in_flight - scrum.overdue, color: COLORS.series[0], icon: null },
    { label: 'Overdue', value: scrum.overdue, color: COLORS.critical, icon: null },
  ]
  return (
    <ChartCard title="Scrum task completion" subtitle={`${scrum.completion_pct}% of ${scrum.total} tasks completed`} empty={scrum.total === 0} height={200}
      table={{ columns: [{ key: 'label', label: 'Tasks' }, { key: 'value', label: 'Count' }], rows: slices }} summary={`${scrum.completed} completed, ${scrum.overdue} overdue of ${scrum.total} tasks`}>
      <Donut slices={slices} />
    </ChartCard>
  )
}

function StudentList({ rows, title = 'Student progress', subtitle = 'Lowest progress first' }) {
  return (
    <section className="card" aria-label={title}>
      <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
      <p className="mb-2 text-xs text-slate-500">{subtitle}</p>
      {rows.length === 0 && <p className="py-6 text-center text-sm text-slate-500">No projects yet.</p>}
      <ul className="divide-y divide-slate-100">
        {rows.map((r) => (
          <li key={`${r.project_id}-${r.registration_no}`} className="flex items-center justify-between gap-3 py-2 text-sm">
            <div className="min-w-0"><Link className="font-medium text-brand hover:underline" to={`/projects/${r.project_id}`}>{r.student}</Link><div className="text-xs text-slate-500">{r.stage}</div></div>
            <div className="flex items-center gap-2">{r.is_delayed && <StatusBadge tone="red">Delayed</StatusBadge>}<ProgressBar value={r.progress} /></div>
          </li>
        ))}
      </ul>
    </section>
  )
}

// ------------------------------------------------------------------- admin
export function AdminDashboard() {
  return (
    <Shell filterable title="Institution dashboard" subtitle="Live overview across all OUs, domains and batches.">
      {(d) => {
        const c = d.counts
        return (
          <>
            <StatGrid>
              <StatCard label="OUs" value={c.ous} /><StatCard label="Domains" value={c.domains} /><StatCard label="Batches" value={c.batches} />
              <StatCard label="Students" value={c.students} /><StatCard label="Mentors" value={c.mentors} /><StatCard label="Problem statements" value={c.problem_statements} />
              <StatCard label="In progress" value={c.in_progress} /><StatCard label="Awaiting SRS approval" value={c.awaiting_srs_approval} />
              <StatCard label="Pending weekly reviews" value={c.pending_reviews} /><StatCard label="Completed" value={c.completed} tone="good" />
              <StatCard label="Delayed" value={c.delayed} tone={c.delayed ? 'critical' : 'default'} /><StatCard label="Total projects" value={c.projects_total} />
            </StatGrid>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <StatusChart split={d.status_split} />
              <StageChart rows={d.stage_distribution} />
              <ChartCard title="OU-wise project distribution" empty={noneIn(d.ou_distribution, 'projects')}
                table={{ columns: [{ key: 'name', label: 'OU' }, { key: 'projects', label: 'Projects' }, { key: 'completed', label: 'Completed' }], rows: d.ou_distribution }}>
                <Bars data={d.ou_distribution} categoryKey="name" series={[{ key: 'projects', label: 'Projects' }, { key: 'completed', label: 'Completed' }]} />
              </ChartCard>
              <ChartCard title="Domain-wise project distribution" empty={noneIn(d.domain_distribution, 'projects')}
                table={{ columns: [{ key: 'name', label: 'Domain' }, { key: 'projects', label: 'Projects' }, { key: 'completed', label: 'Completed' }], rows: d.domain_distribution }}>
                <Bars data={d.domain_distribution} categoryKey="name" series={[{ key: 'projects', label: 'Projects' }, { key: 'completed', label: 'Completed' }]} />
              </ChartCard>
              <BatchProgress rows={d.batch_progress} />
              <ChartCard title="Student participation by OU" subtitle="Students with and without an allocated project" empty={d.student_participation.every((r) => !r.with_project && !r.without_project)}
                table={{ columns: [{ key: 'ou', label: 'OU' }, { key: 'with_project', label: 'With project' }, { key: 'without_project', label: 'Without project' }], rows: d.student_participation }}>
                <Bars data={d.student_participation} categoryKey="ou" series={[{ key: 'with_project', label: 'With project' }, { key: 'without_project', label: 'Without project' }]} stacked />
              </ChartCard>
              <ChartCard title="Mentor workload" subtitle="Projects per mentor" empty={d.mentor_workload.length === 0}
                table={{ columns: [{ key: 'mentor', label: 'Mentor' }, { key: 'projects', label: 'Projects' }], rows: d.mentor_workload }} height={Math.max(220, d.mentor_workload.length * 34)}>
                <Bars data={d.mentor_workload} categoryKey="mentor" series={[{ key: 'projects', label: 'Projects' }]} horizontal />
              </ChartCard>
              <WeeklyStatusChart rows={d.review_completion.by_week} title={`Review completion – ${d.review_completion.rate_pct}% (${d.review_completion.submitted}/${d.review_completion.total})`} />
              <ChartCard title="Average evaluation score by week" subtitle="Mean percentage of submitted reviews" empty={d.average_scores.every((r) => !r.reviews)}
                table={{ columns: [{ key: 'week', label: 'Week' }, { key: 'average', label: 'Average %' }, { key: 'reviews', label: 'Reviews' }], rows: d.average_scores }}>
                <Bars data={d.average_scores} categoryKey="week" series={[{ key: 'average', label: 'Average score' }]} domain={[0, 100]} unit="%" />
              </ChartCard>
            </div>
          </>
        )
      }}
    </Shell>
  )
}

// -------------------------------------------------------------------- lead
export function LeadDashboard() {
  return (
    <Shell filterable title="Domain dashboard" subtitle="Batches, mentors and projects in your domain(s).">
      {(d) => {
        const c = d.counts
        return (
          <>
            <StatGrid>
              <StatCard label="Batches" value={c.batches} /><StatCard label="Students" value={c.students} /><StatCard label="Mentors" value={c.mentors} />
              <StatCard label="Problem statements" value={c.problem_statements} /><StatCard label="Projects allocated" value={c.projects_allocated} />
              <StatCard label="SRS pending approval" value={c.srs_pending_approval} /><StatCard label="Under implementation" value={c.under_implementation} />
              <StatCard label="Weekly reviews pending" value={c.reviews_pending} /><StatCard label="Completed" value={c.completed} tone="good" />
              <StatCard label="Delayed" value={c.delayed} tone={c.delayed ? 'critical' : 'default'} />
              <StatCard label="Date changes to approve" value={c.date_requests_pending ?? 0} tone={c.date_requests_pending ? 'warning' : 'default'} />
            </StatGrid>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <StatusChart split={d.status_split} />
              <BatchProgress rows={d.batch_progress} />
              <ChartCard title="Mentor-wise review completion" subtitle="Submitted vs still to do" empty={d.mentor_review_completion.length === 0}
                table={{ columns: [{ key: 'mentor', label: 'Mentor' }, { key: 'projects', label: 'Projects' }, { key: 'submitted', label: 'Submitted' }, { key: 'pending', label: 'Pending' }, { key: 'completion_pct', label: 'Completion %' }], rows: d.mentor_review_completion }}>
                <Bars data={d.mentor_review_completion} categoryKey="mentor" series={[{ key: 'submitted', label: 'Submitted' }, { key: 'pending', label: 'Pending' }]} stacked />
              </ChartCard>
              <ChartCard title="SRS approval status" empty={noneIn(d.srs_status)} table={{ columns: [{ key: 'label', label: 'Status' }, { key: 'count', label: 'Projects' }], rows: d.srs_status }}>
                <Bars data={d.srs_status} categoryKey="label" series={[{ key: 'count', label: 'Projects' }]} />
              </ChartCard>
              <WeeklyStatusChart rows={d.weekly_evaluation_status} />
              <ScrumSummary scrum={d.scrum} />
              <StageChart rows={d.stage_distribution} />
              <StudentList rows={d.student_progress} />
            </div>
          </>
        )
      }}
    </Shell>
  )
}

// ------------------------------------------------------------------ mentor
function QueueCard({ title, empty, children }) {
  return <section className="card" aria-label={title}><h3 className="mb-2 text-sm font-semibold text-slate-900">{title}</h3>{children || <p className="py-4 text-center text-sm text-slate-500">{empty}</p>}</section>
}

export function MentorDashboard() {
  return (
    <Shell filterable title="Mentor dashboard" subtitle="Your batches, approvals and evaluations.">
      {(d) => {
        const c = d.counts
        return (
          <>
            <StatGrid>
              <StatCard label="Assigned batches" value={c.assigned_batches} /><StatCard label="Students" value={c.students} /><StatCard label="Active projects" value={c.active_projects} />
              <StatCard label="SRS pending approval" value={c.srs_pending_approval} /><StatCard label="SRS approved" value={c.srs_approved} />
              <StatCard label="Reviews pending" value={c.reviews_pending} /><StatCard label="Reviews completed" value={c.reviews_completed} tone="good" />
              <StatCard label="Need attention" value={c.needs_attention} tone={c.needs_attention ? 'critical' : 'default'} /><StatCard label="Nearing completion" value={c.nearing_completion} />
            </StatGrid>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <QueueCard title="SRS approval queue" empty="Nothing is waiting for your review.">
                {d.srs_queue.length > 0 && <ul className="divide-y divide-slate-100">{d.srs_queue.map((q) => (
                  <li key={q.project_id} className="flex items-center justify-between py-2 text-sm"><div><div className="font-medium">{q.title}</div><div className="text-xs text-slate-500">{q.students.join(', ')} · v{q.version}</div></div>
                    <Link className="btn-secondary" to={`/srs/${q.project_id}`}>Review</Link></li>))}</ul>}
              </QueueCard>
              <QueueCard title="Weekly review queue" empty="No evaluations are pending.">
                {d.review_queue.length > 0 && <ul className="divide-y divide-slate-100">{d.review_queue.map((q) => (
                  <li key={q.review_id} className="flex items-center justify-between py-2 text-sm"><div><div className="font-medium">{q.project} · Week {q.week_no}</div>
                    <div className={`text-xs ${q.is_overdue ? 'font-medium text-red-600' : 'text-slate-500'}`}>{q.students.join(', ')} · due {fmtDate(q.due_date)}{q.is_overdue ? ' · overdue' : ''}</div></div>
                    <Link className="btn-secondary" to={`/reviews/${q.review_id}`}>Evaluate</Link></li>))}</ul>}
              </QueueCard>
              <QueueCard title="Students requiring attention" empty="Everyone is on track.">
                {d.students_requiring_attention.length > 0 && <ul className="divide-y divide-slate-100">{d.students_requiring_attention.map((a) => (
                  <li key={a.project_id} className="py-2 text-sm"><Link className="font-medium text-brand hover:underline" to={`/projects/${a.project_id}`}>{a.title}</Link>
                    <span className="text-slate-500"> · {a.students.join(', ')}</span><ul className="mt-0.5 list-disc pl-5 text-xs text-red-700">{a.reasons.map((r) => <li key={r}>{r}</li>)}</ul></li>))}</ul>}
              </QueueCard>
              <QueueCard title="Projects nearing completion" empty="No project is at 75% or more yet.">
                {d.nearing_completion.length > 0 && <ul className="divide-y divide-slate-100">{d.nearing_completion.map((n) => (
                  <li key={n.project_id} className="flex items-center justify-between py-2 text-sm"><Link className="font-medium text-brand hover:underline" to={`/projects/${n.project_id}`}>{n.title}</Link><ProgressBar value={n.progress} /></li>))}</ul>}
              </QueueCard>
              <StageChart rows={d.stage_distribution} />
              <WeeklyStatusChart rows={d.weekly_evaluation_status} title="Evaluation status by week" />
              <ScrumSummary scrum={d.scrum} />
              <StudentList rows={d.student_progress} />
            </div>
          </>
        )
      }}
    </Shell>
  )
}

// ----------------------------------------------------------------- student
export function StudentDashboard() {
  return (
    <Shell title="My dashboard" subtitle="Your project at a glance.">
      {(d) => {
        if (!d.project) {
          return <div className="card text-sm text-slate-600">No project has been allocated to you yet{d.batch ? ` (batch ${d.batch.code})` : ''}. You will be notified as soon as one is.</div>
        }
        const p = d.project
        const chartRows = d.reviews.filter((r) => r.status === 'submitted').map((r) => ({ label: r.label, percentage: r.percentage, obtained: r.obtained, max: r.max }))
        const SRS_TONE = { approved: 'green', submitted: 'blue', under_review: 'orange', changes_requested: 'red', not_submitted: 'grey' }
        return (
          <>
            <section className="card space-y-3" aria-label="Project summary">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold text-slate-900">{p.title}</h2>
                  <p className="text-sm text-slate-500">{d.problem_statement.ps_code} · {d.domain || 'No domain'} · Batch {d.batch.code} – {d.batch.name}</p>
                </div>
                <div className="flex items-center gap-2">{p.is_delayed && <StatusBadge tone="red">Delayed</StatusBadge>}<StageBadge stage={p.stage} label={p.stage_label} /></div>
              </div>
              {p.is_delayed && <Alert type="warning">{p.delay_reasons.join(' · ')}</Alert>}
              <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
                <div><div className="text-slate-500">Progress</div><ProgressBar value={p.progress} /></div>
                <div><div className="text-slate-500">Mentor</div><div className="font-medium">{d.mentors.length ? d.mentors.join(', ') : 'Not assigned'}</div></div>
                <div><div className="text-slate-500">Schedule</div><div className="font-medium">{fmtDate(p.start_date)} → {fmtDate(p.target_end_date)}</div></div>
                <div><div className="text-slate-500">SRS</div><StatusBadge tone={SRS_TONE[d.srs_status]}>{d.srs_status_label}</StatusBadge></div>
              </div>
              <div className="flex flex-wrap gap-2 text-sm">
                <Link className="btn-secondary" to="/student/project">Project</Link><Link className="btn-secondary" to="/student/srs">SRS</Link>
                <Link className="btn-secondary" to="/student/scrum">Scrum board</Link><Link className="btn-secondary" to="/student/reviews">Weekly reviews</Link>
                <Link className="btn-secondary" to={`/problem-statements/${d.problem_statement.id}`}>Problem statement</Link>
              </div>
            </section>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <ChartCard title="Weekly review scores" subtitle={d.overall_score_pct == null ? 'No review has been published yet' : `Overall ${d.overall_score_pct}%`} empty={chartRows.length === 0}
                table={{ columns: [{ key: 'label', label: 'Week' }, { key: 'obtained', label: 'Marks' }, { key: 'max', label: 'Out of' }, { key: 'percentage', label: '%' }], rows: chartRows }}>
                <Bars data={chartRows} categoryKey="label" series={[{ key: 'percentage', label: 'Score' }]} domain={[0, 100]} unit="%" />
              </ChartCard>
              <section className="card space-y-2" aria-label="Review status">
                <h3 className="text-sm font-semibold text-slate-900">Review status</h3>
                <ul className="grid grid-cols-2 gap-2 text-sm">{d.reviews.map((r) => (
                  <li key={r.week_no} className="rounded-lg border border-slate-200 p-2"><div className="font-medium">{r.label}</div><div className="text-xs text-slate-500">Due {fmtDate(r.due_date)}</div>
                    <StatusBadge tone={r.status === 'submitted' ? 'green' : 'grey'}>{r.status === 'submitted' ? `${r.percentage}%` : 'Pending'}</StatusBadge></li>))}</ul>
              </section>
              <section className="card space-y-2" aria-label="Latest mentor feedback">
                <h3 className="text-sm font-semibold text-slate-900">Latest mentor feedback</h3>
                {d.latest_mentor_feedback?.remarks ? <p className="whitespace-pre-wrap text-sm text-slate-800">“{d.latest_mentor_feedback.remarks}” <span className="text-xs text-slate-500">– Week {d.latest_mentor_feedback.week_no} review</span></p> : <p className="text-sm text-slate-500">No feedback yet.</p>}
                {d.latest_srs_feedback?.remarks && <p className="text-sm text-slate-700"><span className="font-medium">SRS ({d.latest_srs_feedback.decision.replace(/_/g, ' ')}):</span> “{d.latest_srs_feedback.remarks}”</p>}
              </section>
              <section className="card space-y-2" aria-label="Scrum summary">
                <h3 className="text-sm font-semibold text-slate-900">Scrum tasks</h3>
                <div className="grid grid-cols-3 gap-2 text-center text-sm">
                  <div><div className="text-xl font-semibold">{d.scrum.total}</div><div className="text-xs text-slate-500">Total</div></div>
                  <div><div className="text-xl font-semibold text-green-700">{d.scrum.completed}</div><div className="text-xs text-slate-500">Completed</div></div>
                  <div><div className={`text-xl font-semibold ${d.scrum.overdue ? 'text-red-700' : ''}`}>{d.scrum.overdue}</div><div className="text-xs text-slate-500">Overdue</div></div>
                </div>
                <div className="text-sm">{d.github_url ? <a className="text-brand underline" href={d.github_url} target="_blank" rel="noreferrer noopener">{d.github_url}</a> : <span className="text-slate-500">No GitHub repository added yet.</span>}</div>
              </section>
            </div>
            <section className="card" aria-label="Project timeline">
              <h3 className="mb-3 text-sm font-semibold text-slate-900">Project timeline</h3>
              <ol className="space-y-2 border-l-2 border-slate-200 pl-4">{d.timeline.map((t, i) => (
                <li key={i} className="text-sm"><span className="font-medium">{t.label}</span>{t.is_reopen && <span className="text-orange-700"> (reopened)</span>}<div className="text-xs text-slate-500">{new Date(`${t.at}Z`).toLocaleString()}</div></li>))}</ol>
            </section>
          </>
        )
      }}
    </Shell>
  )
}
