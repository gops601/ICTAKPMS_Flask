import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AdminDashboard, LeadDashboard, MentorDashboard, StudentDashboard } from './pages/common/Dashboards'
import ReportsPage from './pages/common/ReportsPage'
import { ChartCard, Donut, statusSlices } from './components/charts'
import * as svc from './services/adminService'

let mockUser = { id: 1, name: 'Ada', role: 'admin' }
vi.mock('./context/AuthContext', async () => {
  const actual = await vi.importActual('./context/AuthContext')
  return { ...actual, useAuth: () => ({ user: mockUser }) }
})
vi.mock('./services/adminService', async () => {
  const actual = await vi.importActual('./services/adminService')
  return {
    ...actual,
    dashboardService: { get: vi.fn() },
    reportService: { list: vi.fn(), get: vi.fn(), download: vi.fn() },
    batchService: { list: vi.fn() },
    domainService: { list: vi.fn() },
    ouService: { list: vi.fn() },
  }
})

const STAGES = ['allocated', 'srs_preparation', 'srs_submitted', 'srs_under_review', 'srs_changes_requested', 'srs_approved', 'implementation', 'final_evaluation', 'completed']
const stageRows = (counts = {}) => STAGES.map((s) => ({ stage: s, label: s.replace(/_/g, ' '), count: counts[s] || 0 }))
const WEEKS = (v = {}) => [1, 2, 3, 4].map((w) => ({ week: `Week ${w}`, submitted: v.s || 0, in_progress: v.i || 0, pending: v.p || 0 }))

const ADMIN = {
  role: 'admin',
  counts: { ous: 4, domains: 6, batches: 2, students: 5, mentors: 2, problem_statements: 3, projects_total: 4, in_progress: 3, awaiting_srs_approval: 1, pending_reviews: 1, completed: 1, delayed: 2 },
  status_split: { completed: 1, delayed: 2, ongoing: 1 }, stage_distribution: stageRows({ implementation: 1, completed: 1 }),
  ou_distribution: [{ name: 'Retail OU', projects: 4, completed: 1 }], domain_distribution: [{ name: 'AI & ML', projects: 3, completed: 1 }],
  batch_progress: [{ batch: 'B1', average_progress: 42.5, projects: 3 }], student_participation: [{ ou: 'Retail OU', with_project: 4, without_project: 1 }],
  mentor_workload: [{ mentor: 'Mia One', projects: 3 }], review_completion: { submitted: 6, total: 16, rate_pct: 37.5, by_week: WEEKS({ s: 1, p: 1 }) },
  average_scores: [{ week: 'Week 1', average: 85, reviews: 2 }, { week: 'Week 2', average: 0, reviews: 0 }, { week: 'Week 3', average: 0, reviews: 0 }, { week: 'Week 4', average: 0, reviews: 0 }],
}

beforeEach(() => {
  vi.clearAllMocks()
  mockUser = { id: 1, name: 'Ada', role: 'admin' }
  svc.batchService.list.mockResolvedValue({ items: [{ id: 5, code: 'B1', name: 'Batch One' }, { id: 6, code: 'B2', name: 'Batch Two' }], meta: {} })
})

const renderIn = (ui) => render(<MemoryRouter>{ui}</MemoryRouter>)
const tile = (label) => screen.getByRole('group', { name: label })

describe('chart building blocks', () => {
  it('ChartCard offers a table view with the exact values and a way back', async () => {
    render(<ChartCard title="Demo" table={{ columns: [{ key: 'a', label: 'Name' }, { key: 'b', label: 'Count' }], rows: [{ a: 'x', b: 3 }, { a: 'y', b: null }] }}><div>chart-body</div></ChartCard>)
    expect(screen.getByRole('img', { name: 'Demo' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /view as table/i }))
    expect(screen.getByRole('columnheader', { name: 'Count' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '3' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '—' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /view chart/i }))
    expect(screen.getByText('chart-body')).toBeInTheDocument()
  })

  it('ChartCard shows an empty state instead of an empty plot', () => {
    render(<ChartCard title="Empty" empty table={{ columns: [], rows: [] }}><div>chart-body</div></ChartCard>)
    expect(screen.getByText(/no data yet/i)).toBeInTheDocument()
    expect(screen.queryByText('chart-body')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /table/i })).not.toBeInTheDocument()
  })

  it('Donut legend pairs every status colour with an icon, label, count and percentage', () => {
    render(<Donut slices={statusSlices({ completed: 1, ongoing: 1, delayed: 2 })} />)
    const legend = screen.getByLabelText('Legend')
    expect(within(legend).getByText('Delayed').closest('li')).toHaveTextContent('2')
    expect(within(legend).getByText('Delayed').closest('li')).toHaveTextContent('50%')
    expect(legend.querySelectorAll('svg').length).toBe(3)                               // icon on each status row
  })
})

describe('admin dashboard', () => {
  it('shows live counts, flags delays with an icon + label, and fills charts from the API', async () => {
    svc.dashboardService.get.mockResolvedValue(ADMIN)
    renderIn(<AdminDashboard />)
    expect(await screen.findByRole('heading', { name: /institution dashboard/i })).toBeInTheDocument()
    for (const [label, value] of [['OUs', '4'], ['Domains', '6'], ['Students', '5'], ['Mentors', '2'], ['Projects on shelf', '3'], ['In progress', '3'],
      ['Awaiting SRS approval', '1'], ['Pending weekly reviews', '1'], ['Completed', '1'], ['Delayed', '2']]) {
      expect(within(tile(label)).getByText(value)).toBeInTheDocument()
    }
    expect(tile('Delayed').querySelector('svg')).not.toBeNull()
    for (const t of ['Completed vs ongoing vs delayed', 'Project stage distribution', 'OU-wise project distribution', 'Domain-wise project distribution', 'Batch-wise progress',
      'Mentor workload', 'Average evaluation score by week']) expect(screen.getByRole('region', { name: t })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: /review completion – 37.5% \(6\/16\)/i })).toBeInTheDocument()
  })

  it('exposes exact chart values through the table view', async () => {
    svc.dashboardService.get.mockResolvedValue(ADMIN)
    renderIn(<AdminDashboard />)
    const card = await screen.findByRole('region', { name: 'Batch-wise progress' })
    await userEvent.click(within(card).getByRole('button', { name: /view as table/i }))
    const row = within(card).getByRole('cell', { name: 'B1' }).closest('tr')
    expect(row).toHaveTextContent('42.5')
    const stages = screen.getByRole('region', { name: 'Project stage distribution' })
    await userEvent.click(within(stages).getByRole('button', { name: /view as table/i }))
    expect(within(stages).getByRole('cell', { name: 'implementation' }).closest('tr')).toHaveTextContent('1')
  })

  it('does not paint a zero Delayed tile as an alert and shows empty states with no data', async () => {
    svc.dashboardService.get.mockResolvedValue({ ...ADMIN, counts: { ...ADMIN.counts, delayed: 0, projects_total: 0 }, status_split: { completed: 0, delayed: 0, ongoing: 0 },
      stage_distribution: stageRows(), ou_distribution: [], domain_distribution: [], batch_progress: [], mentor_workload: [], student_participation: [{ ou: 'Retail OU', with_project: 0, without_project: 0 }],
      review_completion: { submitted: 0, total: 0, rate_pct: 0, by_week: WEEKS() }, average_scores: ADMIN.average_scores.map((a) => ({ ...a, reviews: 0 })) })
    renderIn(<AdminDashboard />)
    await screen.findByRole('heading', { name: /institution dashboard/i })
    expect(tile('Delayed').querySelector('svg')).toBeNull()
    expect(screen.getAllByText(/no data yet/i).length).toBeGreaterThanOrEqual(6)
  })

  it('shows the API error instead of a blank page', async () => {
    svc.dashboardService.get.mockRejectedValue({ response: { status: 500, data: { message: 'Internal server error' } } })
    renderIn(<AdminDashboard />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Internal server error')
  })
})

describe('batch filter on dashboards', () => {
  it.each([['admin', AdminDashboard, ADMIN], ['domain_lead', LeadDashboard, null], ['mentor', MentorDashboard, null]])(
    '%s can narrow the dashboard to one batch and back', async (role, Dash, data) => {
      mockUser = { id: 2, name: 'U', role }
      const payload = data || (role === 'mentor'
        ? { role, counts: { assigned_batches: 1, students: 0, active_projects: 0, srs_pending_approval: 0, srs_approved: 0, reviews_pending: 0, reviews_completed: 0, needs_attention: 0, nearing_completion: 0 }, srs_queue: [], review_queue: [], students_requiring_attention: [], nearing_completion: [], stage_distribution: stageRows(), scrum: { total: 0, completed: 0, overdue: 0, in_flight: 0, completion_pct: 0 }, student_progress: [], weekly_evaluation_status: WEEKS() }
        : { role, counts: { batches: 1, students: 0, mentors: 0, problem_statements: 0, projects_allocated: 0, srs_pending_approval: 0, under_implementation: 0, reviews_pending: 0, completed: 0, delayed: 0 }, status_split: { completed: 0, delayed: 0, ongoing: 0 }, stage_distribution: stageRows(), batch_progress: [], mentor_review_completion: [], srs_status: [], weekly_evaluation_status: WEEKS(), scrum: { total: 0, completed: 0, overdue: 0, in_flight: 0, completion_pct: 0 }, average_scores: [], student_progress: [] })
      svc.dashboardService.get.mockResolvedValue(payload)
      renderIn(<Dash />)
      const select = await screen.findByLabelText('Filter by batch')
      await waitFor(() => expect(within(select).getAllByRole('option')).toHaveLength(3))
      expect(svc.dashboardService.get).toHaveBeenLastCalledWith(undefined)
      await userEvent.selectOptions(select, '5')
      await waitFor(() => expect(svc.dashboardService.get).toHaveBeenLastCalledWith({ batch_id: '5' }))
      expect(await screen.findByText(/filtered to the selected batch/i)).toBeInTheDocument()
      await userEvent.selectOptions(screen.getByLabelText('Filter by batch'), '')
      await waitFor(() => expect(svc.dashboardService.get).toHaveBeenLastCalledWith(undefined))
    })

  it('lists only the batches the API returns and keeps the selector when a filtered load fails', async () => {
    svc.dashboardService.get.mockResolvedValueOnce(ADMIN).mockRejectedValueOnce({ response: { status: 404, data: { message: 'Batch not found' } } })
    renderIn(<AdminDashboard />)
    const select = await screen.findByLabelText('Filter by batch')
    await waitFor(() => expect(within(select).getAllByRole('option')).toHaveLength(3))
    expect(within(select).getAllByRole('option').map((o) => o.textContent)).toEqual(['All batches', 'B1 – Batch One', 'B2 – Batch Two'])
    await userEvent.selectOptions(select, '6')
    expect(await screen.findByRole('alert')).toHaveTextContent('Batch not found')
    expect(screen.getByLabelText('Filter by batch')).toBeInTheDocument()
  })

  it('students get no batch selector', async () => {
    mockUser = { id: 9, name: 'Stu', role: 'student' }
    svc.dashboardService.get.mockResolvedValue({ role: 'student', project: null, batch: { code: 'B1', name: 'Batch One' } })
    renderIn(<StudentDashboard />)
    await screen.findByText(/no project has been allocated/i)
    expect(screen.queryByLabelText('Filter by batch')).not.toBeInTheDocument()
  })
})

describe('domain lead dashboard', () => {
  const LEAD = {
    role: 'domain_lead',
    counts: { batches: 1, students: 4, mentors: 1, problem_statements: 2, projects_allocated: 3, srs_pending_approval: 1, under_implementation: 1, reviews_pending: 3, completed: 1, delayed: 1 },
    status_split: { completed: 1, delayed: 1, ongoing: 1 }, stage_distribution: stageRows({ implementation: 1 }), batch_progress: [{ batch: 'B1', average_progress: 42.5, projects: 3 }],
    mentor_review_completion: [{ mentor: 'Mia One', projects: 3, submitted: 6, pending: 3, completion_pct: 66.7 }],
    srs_status: [{ status: 'approved', label: 'Approved', count: 2 }], weekly_evaluation_status: WEEKS({ s: 1 }),
    scrum: { total: 2, completed: 1, overdue: 1, in_flight: 1, completion_pct: 50 }, average_scores: ADMIN.average_scores,
    student_progress: [{ student: 'Student s2', registration_no: 'S2', project_id: 12, stage: 'SRS Submitted', progress: 0, is_delayed: false },
      { student: 'Student s1', registration_no: 'S1', project_id: 11, stage: 'Implementation', progress: 57.5, is_delayed: true }],
  }
  it('shows domain stats, scrum completion and student progress linking to projects', async () => {
    mockUser = { id: 3, name: 'Lea', role: 'domain_lead' }
    svc.dashboardService.get.mockResolvedValue(LEAD)
    renderIn(<LeadDashboard />)
    expect(await screen.findByRole('heading', { name: /domain dashboard/i })).toBeInTheDocument()
    expect(within(tile('Projects allocated')).getByText('3')).toBeInTheDocument()
    expect(within(tile('Weekly reviews pending')).getByText('3')).toBeInTheDocument()
    expect(screen.getByText(/50% of 2 tasks completed/)).toBeInTheDocument()
    const students = screen.getByRole('region', { name: 'Student progress' })
    expect(within(students).getByRole('link', { name: 'Student s2' })).toHaveAttribute('href', '/projects/12')
    expect(within(students).getAllByText('Delayed')).toHaveLength(1)
    const mentors = screen.getByRole('region', { name: 'Mentor-wise review completion' })
    await userEvent.click(within(mentors).getByRole('button', { name: /view as table/i }))
    expect(within(mentors).getByRole('cell', { name: 'Mia One' }).closest('tr')).toHaveTextContent('66.7')
  })
})

describe('mentor dashboard', () => {
  const MENTOR = {
    role: 'mentor', counts: { assigned_batches: 1, students: 3, active_projects: 2, srs_pending_approval: 1, srs_approved: 2, reviews_pending: 3, reviews_completed: 6, needs_attention: 2, nearing_completion: 1 },
    srs_queue: [{ project_id: 12, title: 'Beta', students: ['Student s2'], version: 2 }],
    review_queue: [{ review_id: 40, week_no: 3, due_date: '2026-03-01', is_overdue: true, status: 'pending', project: 'Alpha', students: ['Student s1'] }],
    students_requiring_attention: [{ project_id: 11, title: 'Alpha', students: ['Student s1'], progress: 57.5, reasons: ['1 Scrum task(s) overdue'] }],
    nearing_completion: [{ project_id: 11, title: 'Alpha', progress: 80 }], stage_distribution: stageRows({ implementation: 1 }),
    scrum: { total: 0, completed: 0, overdue: 0, in_flight: 0, completion_pct: 0 }, student_progress: [], weekly_evaluation_status: WEEKS(),
  }
  it('shows approval and evaluation queues with direct action links', async () => {
    mockUser = { id: 4, name: 'Mia', role: 'mentor' }
    svc.dashboardService.get.mockResolvedValue(MENTOR)
    renderIn(<MentorDashboard />)
    expect(await screen.findByRole('heading', { name: /mentor dashboard/i })).toBeInTheDocument()
    expect(within(tile('Need attention')).getByText('2')).toBeInTheDocument()
    const srs = screen.getByRole('region', { name: 'SRS approval queue' })
    expect(within(srs).getByText(/v2/)).toBeInTheDocument()
    expect(within(srs).getByRole('link', { name: 'Review' })).toHaveAttribute('href', '/srs/12')
    const reviews = screen.getByRole('region', { name: 'Weekly review queue' })
    expect(within(reviews).getByText(/overdue/)).toBeInTheDocument()
    expect(within(reviews).getByRole('link', { name: 'Evaluate' })).toHaveAttribute('href', '/reviews/40')
    const attention = screen.getByRole('region', { name: 'Students requiring attention' })
    expect(within(attention).getByText('1 Scrum task(s) overdue')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Projects nearing completion' })).getByRole('link', { name: 'Alpha' })).toHaveAttribute('href', '/projects/11')
  })

  it('shows friendly empty states', async () => {
    mockUser = { id: 4, name: 'Mia', role: 'mentor' }
    svc.dashboardService.get.mockResolvedValue({ ...MENTOR, counts: { ...MENTOR.counts, needs_attention: 0 }, srs_queue: [], review_queue: [], students_requiring_attention: [], nearing_completion: [] })
    renderIn(<MentorDashboard />)
    expect(await screen.findByText(/nothing is waiting for your review/i)).toBeInTheDocument()
    expect(screen.getByText(/no evaluations are pending/i)).toBeInTheDocument()
    expect(screen.getByText(/everyone is on track/i)).toBeInTheDocument()
    expect(screen.getByText(/at 75% or more/i)).toBeInTheDocument()
  })
})

describe('student dashboard', () => {
  const STUDENT = {
    role: 'student',
    project: { id: 11, title: 'Smart Attendance', stage: 'implementation', stage_label: 'Implementation', progress: 57.5, is_delayed: true, delay_reasons: ['1 Scrum task(s) overdue'], start_date: '2026-03-02', target_end_date: '2026-03-30' },
    problem_statement: { id: 3, ps_code: 'PS-1', title: 'Attendance' }, domain: 'AI & ML', batch: { code: 'B1', name: 'Batch One' }, mentors: ['Mia One'],
    srs_status: 'approved', srs_status_label: 'Approved', latest_srs_feedback: { decision: 'approved', remarks: 'Looks good' },
    reviews: [{ week_no: 1, label: 'Week 1', due_date: '2026-03-09', status: 'submitted' },
      { week_no: 2, label: 'Week 2', due_date: '2026-03-16', status: 'pending' }, { week_no: 3, label: 'Week 3', due_date: '2026-03-23', status: 'pending' }, { week_no: 4, label: 'Week 4', due_date: '2026-03-30', status: 'pending' }],
    latest_mentor_feedback: { week_no: 1, remarks: 'Good start', mentor: null }, scrum: { total: 2, completed: 1, overdue: 1 }, github_url: 'https://github.com/o/alpha',
    timeline: [{ stage: 'allocated', label: 'Project Allocated', at: '2026-03-02T10:00:00', is_reopen: false }, { stage: 'implementation', label: 'Implementation', at: '2026-03-05T10:00:00', is_reopen: true }],
  }
  beforeEach(() => { mockUser = { id: 9, name: 'Stu', role: 'student' } })

  it('shows project, mentor, stage, progress, SRS, GitHub, feedback, scrum summary and timeline', async () => {
    svc.dashboardService.get.mockResolvedValue(STUDENT)
    renderIn(<StudentDashboard />)
    const summary = await screen.findByRole('region', { name: 'Project summary' })
    expect(within(summary).getByRole('heading', { name: 'Smart Attendance' })).toBeInTheDocument()
    expect(within(summary).getByText(/PS-1 · AI & ML · Batch B1 – Batch One/)).toBeInTheDocument()
    expect(within(summary).getByText('Mia One')).toBeInTheDocument()
    expect(within(summary).getByText('Approved')).toBeInTheDocument()
    expect(within(summary).getByText('Implementation')).toBeInTheDocument()
    expect(within(summary).getAllByText('Delayed').length).toBeGreaterThan(0)
    expect(screen.getByText(/1 Scrum task\(s\) overdue/)).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Latest mentor feedback' })).getByText(/Good start/)).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Latest mentor feedback' })).getByText(/Looks good/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /github.com\/o\/alpha/ })).toBeInTheDocument()
    const status = screen.getByRole('region', { name: 'Review status' })
    expect(within(status).getByText('Reviewed')).toBeInTheDocument()          // no percentage: students see remarks only
    expect(within(status).getAllByText('Pending')).toHaveLength(3)
    const tl = screen.getByRole('region', { name: 'Project timeline' })
    expect(within(tl).getByText('Project Allocated')).toBeInTheDocument()
    expect(within(tl).getByText(/\(reopened\)/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Scrum board' })).toHaveAttribute('href', '/student/scrum')
  })

  it('shows no scores to students: no score chart and no percentages', async () => {
    svc.dashboardService.get.mockResolvedValue(STUDENT)
    renderIn(<StudentDashboard />)
    await screen.findByRole('region', { name: 'Project summary' })
    expect(screen.queryByRole('region', { name: 'Weekly review scores' })).not.toBeInTheDocument()
    expect(screen.queryByText(/\d+%/, { selector: 'li *' })).not.toBeInTheDocument()
  })

  it('handles a student without a project', async () => {
    svc.dashboardService.get.mockResolvedValue({ role: 'student', project: null, batch: { code: 'B1', name: 'Batch One' } })
    renderIn(<StudentDashboard />)
    expect(await screen.findByText(/no project has been allocated to you yet \(batch B1\)/i)).toBeInTheDocument()
  })

  it('shows a no-feedback state and no GitHub hint when appropriate', async () => {
    svc.dashboardService.get.mockResolvedValue({ ...STUDENT, latest_mentor_feedback: null, latest_srs_feedback: null, github_url: null,
      project: { ...STUDENT.project, is_delayed: false, delay_reasons: [] }, reviews: STUDENT.reviews.map((r) => ({ ...r, status: 'pending' })) })
    renderIn(<StudentDashboard />)
    expect(await screen.findByText(/no feedback yet/i)).toBeInTheDocument()
    expect(screen.getByText(/no github repository added yet/i)).toBeInTheDocument()
  })
})

describe('reports page', () => {
  const REPORT = (over = {}) => ({
    type: 'batch', title: 'Batch-wise report', generated_at: '2026-03-10T08:00:00', filters: {},
    columns: [{ key: 'code', label: 'Batch code' }, { key: 'students', label: 'Students' }, { key: 'avg_progress', label: 'Avg progress %' }],
    rows: [{ code: 'B1', students: 4, avg_progress: 42.5 }, { code: 'B2', students: 1, avg_progress: null }], meta: { page: 1, per_page: 25, total: 2, pages: 1 }, ...over,
  })
  const CATALOGUE = [
    { type: 'ou', title: 'OU-wise report', filters: ['ou_id'] }, { type: 'batch', title: 'Batch-wise report', filters: ['ou_id', 'domain_id', 'batch_id'] },
    { type: 'weekly-evaluations', title: 'Weekly evaluation report', filters: ['batch_id', 'week', 'status'] },
  ]
  beforeEach(() => {
    svc.reportService.list.mockResolvedValue(CATALOGUE)
    svc.reportService.get.mockImplementation((type) => Promise.resolve(REPORT({ type })))
    svc.batchService.list.mockResolvedValue({ items: [{ id: 5, code: 'B1', name: 'Batch One' }], meta: {} })
    svc.domainService.list.mockResolvedValue([{ id: 2, name: 'AI & ML' }])
    svc.ouService.list.mockResolvedValue([{ id: 1, name: 'Retail OU' }])
  })

  it('lists the reports the role may see, previews the first and shows all values', async () => {
    renderIn(<ReportsPage />)
    expect(await screen.findByRole('tab', { name: 'OU-wise' })).toHaveAttribute('aria-selected', 'true')
    await waitFor(() => expect(svc.reportService.get).toHaveBeenCalledWith('ou', { page: 1, per_page: 25 }))
    expect(await screen.findByRole('cell', { name: 'B1' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '42.5' })).toBeInTheDocument()
    expect(screen.getByText(/2 row\(s\) · generated/)).toBeInTheDocument()
    expect(screen.getAllByRole('cell', { name: '—' }).length).toBeGreaterThan(0)       // null rendered as a dash
  })

  it('switches report, resets filters, and only offers the filters that report supports', async () => {
    renderIn(<ReportsPage />)
    await screen.findByRole('cell', { name: 'B1' })
    expect(screen.getByLabelText('Filter by OU')).toBeInTheDocument()
    expect(screen.queryByLabelText('Filter by Batch')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: 'Weekly evaluation' }))
    await waitFor(() => expect(svc.reportService.get).toHaveBeenLastCalledWith('weekly-evaluations', { page: 1, per_page: 25 }))
    expect(screen.getByLabelText('Filter by Week')).toBeInTheDocument()
    expect(screen.getByLabelText('Filter by Review status')).toBeInTheDocument()
    expect(screen.queryByLabelText('Filter by OU')).not.toBeInTheDocument()
  })

  it('applies filters to both the preview and the export', async () => {
    svc.reportService.download.mockResolvedValue()
    renderIn(<ReportsPage />)
    await userEvent.click(await screen.findByRole('tab', { name: 'Weekly evaluation' }))
    await userEvent.selectOptions(await screen.findByLabelText('Filter by Week'), '2')
    await userEvent.selectOptions(screen.getByLabelText('Filter by Review status'), 'submitted')
    await waitFor(() => expect(svc.reportService.get).toHaveBeenLastCalledWith('weekly-evaluations', { week: '2', status: 'submitted', page: 1, per_page: 25 }))
    await userEvent.click(screen.getByRole('button', { name: /export csv/i }))
    expect(svc.reportService.download).toHaveBeenCalledWith('weekly-evaluations', 'csv', { week: '2', status: 'submitted' })
    await userEvent.click(screen.getByRole('button', { name: /export excel/i }))
    expect(svc.reportService.download).toHaveBeenLastCalledWith('weekly-evaluations', 'xlsx', { week: '2', status: 'submitted' })
  })

  it('shows an empty state, pagination and server errors', async () => {
    svc.reportService.get.mockResolvedValueOnce(REPORT({ rows: [], meta: { page: 1, per_page: 25, total: 0, pages: 1 } }))
    renderIn(<ReportsPage />)
    expect(await screen.findByText(/no data for these filters/i)).toBeInTheDocument()
    svc.reportService.get.mockResolvedValueOnce(REPORT({ meta: { page: 1, per_page: 25, total: 60, pages: 3 } }))
    await userEvent.click(screen.getByRole('tab', { name: 'Batch-wise' }))
    await userEvent.click(await screen.findByRole('button', { name: /next/i }))
    await waitFor(() => expect(svc.reportService.get).toHaveBeenLastCalledWith('batch', { page: 2, per_page: 25 }))
    svc.reportService.get.mockRejectedValueOnce({ response: { status: 403, data: { message: 'You do not have access to this report' } } })
    await userEvent.click(screen.getByRole('tab', { name: 'OU-wise' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/do not have access/i)
  })

  it('reports export failures and re-enables the buttons', async () => {
    svc.reportService.download.mockRejectedValue({ response: { status: 500, data: { message: 'Export failed on the server' } } })
    renderIn(<ReportsPage />)
    await userEvent.click(await screen.findByRole('button', { name: /export csv/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Export failed on the server')
    expect(screen.getByRole('button', { name: /export csv/i })).toBeEnabled()
  })

  it('mentors do not load OU/domain lists and see their own filters only', async () => {
    mockUser = { id: 4, name: 'Mia', role: 'mentor' }
    renderIn(<ReportsPage title="Project Reports" />)
    expect(await screen.findByRole('heading', { name: 'Project Reports' })).toBeInTheDocument()
    expect(svc.domainService.list).not.toHaveBeenCalled()
    expect(svc.ouService.list).not.toHaveBeenCalled()
    expect(svc.batchService.list).toHaveBeenCalled()
  })
})
