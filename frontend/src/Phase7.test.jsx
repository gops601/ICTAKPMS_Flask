import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ReviewEditor, { computeTotals } from './components/ReviewEditor'
import ReviewDetail from './components/ReviewDetail'
import { EvaluationQueuePage, ProjectReviewsView, ReviewPage, TemplatesPage } from './pages/common/ReviewPages'
import App from './App'
import { AuthProvider } from './context/AuthContext'
import api from './services/api'
import * as svc from './services/adminService'

let mockUser = { id: 4, name: 'Mia', role: 'mentor' }
// The real dashboards are covered in Phase8.test.jsx; here a stub keeps navigation tests independent of chart data.
vi.mock('./pages/common/Dashboards', async () => {
  const React = await import('react')
  const { useAuth } = await import('./context/AuthContext')
  const Stub = () => { const { user } = useAuth(); return React.createElement('h1', null, `Welcome, ${user.name}`) }
  return { AdminDashboard: Stub, LeadDashboard: Stub, MentorDashboard: Stub, StudentDashboard: Stub }
})

vi.mock('./services/api', async () => {
  const actual = await vi.importActual('./services/api')
  return { ...actual, default: { post: vi.fn(), get: vi.fn(() => Promise.resolve({ data: { data: { count: 0 } } })) } }
})
vi.mock('./context/AuthContext', async () => {
  const actual = await vi.importActual('./context/AuthContext')
  return { ...actual, useAuth: () => ({ user: mockUser }) }
})
vi.mock('./services/adminService', async () => {
  const actual = await vi.importActual('./services/adminService')
  return {
    ...actual,
    reviewService: { forProject: vi.fn(), get: vi.fn(), save: vi.fn(), submit: vi.fn(), reopen: vi.fn(), revisions: vi.fn(), applyTemplate: vi.fn(), signoff: vi.fn(), queue: vi.fn() },
    templateService: { list: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(), samples: vi.fn() },
    notificationService: { unreadCount: vi.fn().mockResolvedValue(0), list: vi.fn(), markRead: vi.fn(), readAll: vi.fn() },
  }
})

const crit = (id, name, max, got = null, remarks = null) => ({ id, name, max_marks: max, marks_obtained: got, remarks })
const summary = (over = {}) => ({ total_obtained: 84, total_max: 100, percentage: 84, criteria_count: 4, scored_count: 4, ...over })
const review = (over = {}) => ({
  id: 11, project_id: 7, week_no: 1, due_date: '2026-03-09', is_overdue: false, status: 'draft', status_label: 'In progress', version: 2, visible: true,
  review_date: null, mentor: 'Mia', submitted_at: null, remarks: null, strengths: null, improvements: null, recommendations: null,
  criteria: [], summary: summary({ total_obtained: 0, total_max: 0, percentage: 0, criteria_count: 0, scored_count: 0 }),
  permissions: { can_edit: true, can_submit: true, can_reopen: false, reason: null }, ...over,
})
const submitted = (over = {}) => review({
  status: 'submitted', status_label: 'Submitted', review_date: '2026-03-09', remarks: 'Solid work', strengths: 'Clear scope', improvements: 'More tests', recommendations: 'Read IEEE 830',
  criteria: [crit(1, 'Problem Understanding', 20, 15, 'Good'), crit(2, 'SRS Quality', 30, 24)], summary: summary({ total_obtained: 39, total_max: 50, percentage: 78 }),
  permissions: { can_edit: false, can_submit: false, can_reopen: true, reason: 'Submitted reviews are read-only. Reopen to correct them.' }, ...over,
})

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  mockUser = { id: 4, name: 'Mia', role: 'mentor' }
  svc.notificationService.unreadCount.mockResolvedValue(0)
  svc.templateService.list.mockResolvedValue([])
})

describe('computeTotals', () => {
  it('sums marks and computes the percentage over ALL criteria (unscored count as 0)', () => {
    expect(computeTotals([{ max_marks: '20', marks_obtained: '15' }, { max_marks: '30', marks_obtained: '' }])).toEqual({ max: 50, got: 15, pct: 30 })
    expect(computeTotals([])).toEqual({ max: 0, got: 0, pct: 0 })
    expect(computeTotals([{ max_marks: '3', marks_obtained: '1' }]).pct).toBe(33.33)
  })
})

describe('review editor', () => {
  const renderEditor = (r = review(), onChange = vi.fn()) => { render(<ReviewEditor review={r} onChange={onChange} />); return onChange }

  it('starts empty: nothing is hardcoded, mentors add their own criteria with live totals', async () => {
    renderEditor()
    expect(screen.getByText(/no criteria yet/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /add criterion/i }))
    await userEvent.click(screen.getByRole('button', { name: /add criterion/i }))
    await userEvent.type(screen.getByLabelText('Criterion 1 name'), 'System Design')
    await userEvent.type(screen.getByLabelText('Criterion 1 maximum marks'), '20')
    await userEvent.type(screen.getByLabelText('Criterion 1 marks obtained'), '15')
    await userEvent.type(screen.getByLabelText('Criterion 2 name'), 'Code Quality')
    await userEvent.type(screen.getByLabelText('Criterion 2 maximum marks'), '30')
    const totals = screen.getByLabelText('Totals')
    expect(totals).toHaveTextContent('Total obtained: 15')
    expect(totals).toHaveTextContent('Maximum: 50')
    expect(totals).toHaveTextContent('Percentage: 30%')
    await userEvent.click(screen.getByRole('button', { name: /remove criterion 2/i }))
    expect(screen.getByLabelText('Totals')).toHaveTextContent('Percentage: 75%')
  })

  it('saves a draft with criteria, scores, feedback and the version for conflict detection', async () => {
    const onChange = renderEditor(review({ criteria: [crit(5, 'Design', 40, 30, 'ok')], remarks: 'R' }))
    svc.reviewService.save.mockResolvedValue(review({ version: 3 }))
    await userEvent.type(screen.getByLabelText(/strengths/i), 'Good')
    await userEvent.click(screen.getByRole('button', { name: /save draft/i }))
    await waitFor(() => expect(svc.reviewService.save).toHaveBeenCalled())
    expect(svc.reviewService.save.mock.calls[0][1]).toMatchObject({
      criteria: [{ id: 5, name: 'Design', max_marks: 40, marks_obtained: 30, remarks: 'ok' }], remarks: 'R', strengths: 'Good', version: 2,
    })
    expect(await screen.findByText('Draft saved.')).toBeInTheDocument()
    expect(onChange).toHaveBeenCalled()
  })

  it('blocks invalid criteria locally (empty name, max ≤ 0, marks above max, duplicates)', async () => {
    renderEditor(review({ criteria: [crit(1, '', 10, 11), crit(2, 'A', 0), crit(3, 'a', 5)] }))
    await userEvent.click(screen.getByRole('button', { name: /save draft/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/fix the highlighted/i)
    expect(screen.getByText('Name is required')).toBeInTheDocument()
    expect(screen.getByText('Between 0 and the maximum')).toBeInTheDocument()
    expect(screen.getByText('Max marks must be greater than 0')).toBeInTheDocument()
    expect(screen.getByText('Duplicate criterion')).toBeInTheDocument()
    expect(svc.reviewService.save).not.toHaveBeenCalled()
  })

  it('asks for confirmation before submitting, then submits everything in one call', async () => {
    renderEditor(review({ criteria: [crit(1, 'A', 50, 40), crit(2, 'B', 50, 30)], remarks: 'Good' }))
    svc.reviewService.submit.mockResolvedValue(submitted())
    await userEvent.click(screen.getByRole('button', { name: /submit evaluation/i }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText(/70\/100 \(70%\)/)).toBeInTheDocument()
    expect(svc.reviewService.submit).not.toHaveBeenCalled()
    await userEvent.click(within(dialog).getByRole('button', { name: /^submit$/i }))
    await waitFor(() => expect(svc.reviewService.submit).toHaveBeenCalledWith(11, expect.objectContaining({ remarks: 'Good', version: 2 })))
  })

  it('shows server validation errors against the right rows', async () => {
    renderEditor(review({ criteria: [crit(1, 'A', 10, 5)] }))
    svc.reviewService.submit.mockRejectedValue({ response: { status: 422, data: { message: 'Overall feedback is required to submit', errors: { remarks: 'Overall feedback is required to submit' } } } })
    await userEvent.click(screen.getByRole('button', { name: /submit evaluation/i }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^submit$/i }))
    expect((await screen.findAllByText(/overall feedback is required/i)).length).toBeGreaterThan(0)
  })

  it('applies a template (confirming first if there is work to replace)', async () => {
    svc.templateService.list.mockResolvedValue([{ id: 3, name: 'Week 1 template', total_marks: 100, criteria: [] }])
    renderEditor(review({ criteria: [crit(1, 'Old', 10, 5)] }))
    svc.reviewService.applyTemplate.mockResolvedValue(review({ criteria: [crit(9, 'Design', 40), crit(10, 'Code', 60)] }))
    await userEvent.selectOptions(await screen.findByLabelText(/start from a template/i), '3')
    await userEvent.click(screen.getByRole('button', { name: /^apply$/i }))
    expect(svc.reviewService.applyTemplate).not.toHaveBeenCalled()
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^replace$/i }))
    await waitFor(() => expect(svc.reviewService.applyTemplate).toHaveBeenCalledWith(11, 3))
    expect(await screen.findByDisplayValue('Design')).toBeInTheDocument()
  })

  it('applies a template straight away on an empty review', async () => {
    svc.templateService.list.mockResolvedValue([{ id: 3, name: 'T', total_marks: 10, criteria: [] }])
    renderEditor(review())
    svc.reviewService.applyTemplate.mockResolvedValue(review({ criteria: [crit(9, 'Design', 10)] }))
    await userEvent.selectOptions(await screen.findByLabelText(/start from a template/i), '3')
    await userEvent.click(screen.getByRole('button', { name: /^apply$/i }))
    await waitFor(() => expect(svc.reviewService.applyTemplate).toHaveBeenCalledWith(11, 3))
  })
})

describe('review detail (read-only)', () => {
  it('shows criteria, max, obtained, percentage and all feedback', () => {
    render(<ReviewDetail review={submitted()} />)
    expect(screen.getByText('Problem Understanding')).toBeInTheDocument()
    expect(screen.getByText('Good')).toBeInTheDocument()
    expect(screen.getByText('39 / 50 · 78%')).toBeInTheDocument()
    for (const label of ['Overall feedback', 'Strengths', 'Areas for improvement', 'Recommendations']) expect(screen.getByRole('region', { name: label })).toBeInTheDocument()
    expect(screen.getByText(/Reviewed by Mia · 2026-03-09/)).toBeInTheDocument()
  })
})

describe('review page', () => {
  const renderPage = () => render(<MemoryRouter initialEntries={['/reviews/11']}><Routes><Route path="/reviews/:reviewId" element={<ReviewPage />} /></Routes></MemoryRouter>)

  it('shows the editor for the assigned mentor on an editable review', async () => {
    svc.reviewService.get.mockResolvedValue(review())
    svc.reviewService.revisions.mockResolvedValue([])
    renderPage()
    expect(await screen.findByRole('button', { name: /submit evaluation/i })).toBeInTheDocument()
  })

  it('shows a read-only evaluation and the audit history of a submitted review, with a reopen option', async () => {
    svc.reviewService.get.mockResolvedValue(submitted())
    svc.reviewService.revisions.mockResolvedValue([{ id: 2, reason: 'Mis-keyed marks', changed_by: 'Mia', at: '2026-03-10T08:00:00', snapshot: { summary: summary() } }])
    renderPage()
    expect(await screen.findByText('Problem Understanding')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /submit evaluation/i })).not.toBeInTheDocument()
    const rev = screen.getByRole('listitem', { name: 'Revision 2' })
    expect(within(rev).getByText(/Mis-keyed marks/)).toBeInTheDocument()
    expect(within(rev).getByText(/84 \/ 100 \(84%\)/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reopen to correct/i })).toBeInTheDocument()
  })

  it('requires a reason to reopen, calls the API and returns to the editor', async () => {
    svc.reviewService.get.mockResolvedValue(submitted())
    svc.reviewService.revisions.mockResolvedValue([])
    svc.reviewService.reopen.mockResolvedValue(review({ status: 'reopened', status_label: 'Under revision', criteria: [crit(1, 'A', 10, 5)] }))
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: /reopen to correct/i }))
    const dialog = screen.getByRole('dialog')
    await userEvent.type(within(dialog).getByLabelText(/reason/i), 'Mis-keyed marks')
    await userEvent.click(within(dialog).getByRole('button', { name: /^reopen$/i }))
    await waitFor(() => expect(svc.reviewService.reopen).toHaveBeenCalledWith('11', 'Mis-keyed marks'))
    expect(await screen.findByRole('button', { name: /submit evaluation/i })).toBeInTheDocument()
  })

  it('shows the server error when the reason is too short', async () => {
    svc.reviewService.get.mockResolvedValue(submitted())
    svc.reviewService.revisions.mockResolvedValue([])
    svc.reviewService.reopen.mockRejectedValue({ response: { status: 422, data: { message: 'A reason (at least 5 characters) is required to reopen a review' } } })
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: /reopen to correct/i }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^reopen$/i }))
    expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveTextContent(/at least 5 characters/)
  })

  it('does not offer reopening or history to students and hides unpublished reviews', async () => {
    mockUser = { id: 1, name: 'Stu', role: 'student' }
    svc.reviewService.get.mockResolvedValue({ id: 11, project_id: 7, week_no: 1, status: 'pending', status_label: 'Pending', visible: false, due_date: '2026-03-09', permissions: { can_edit: false, can_reopen: false } })
    renderPage()
    expect(await screen.findByText(/has not been published yet/i)).toBeInTheDocument()
    expect(svc.reviewService.revisions).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: /reopen/i })).not.toBeInTheDocument()
  })

  it('shows the explanation when a week cannot be evaluated yet', async () => {
    svc.reviewService.get.mockResolvedValue(review({ permissions: { can_edit: false, can_reopen: false, reason: 'Weeks 2–4 can be evaluated once implementation has started (SRS approved).' } }))
    svc.reviewService.revisions.mockResolvedValue([])
    renderPage()
    expect(await screen.findByText(/once implementation has started/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /submit evaluation/i })).not.toBeInTheDocument()
  })
})

describe('project reviews view', () => {
  const data = (over = {}) => ({
    project: { id: 7, title: 'Smart Attendance', stage: 'implementation', stage_label: 'Implementation' },
    overall: { reviews_submitted: 1, reviews_total: 4, total_obtained: 39, total_max: 50, percentage: 78, average_percentage: 78, reviews: [] },
    final_evaluation: { signed_off: false, remarks: null, signed_by: null, can_sign_off: false, all_reviews_submitted: false },
    reviews: [
      { ...submitted(), id: 1, week_no: 1 },
      { id: 2, project_id: 7, week_no: 2, status: 'pending', status_label: 'Pending', visible: false, due_date: '2026-03-16', is_overdue: true, permissions: { can_edit: false } },
      { id: 3, project_id: 7, week_no: 3, status: 'pending', status_label: 'Under revision', visible: false, due_date: '2026-03-23', is_overdue: false, permissions: { can_edit: false } },
      { id: 4, project_id: 7, week_no: 4, status: 'pending', status_label: 'Pending', visible: false, due_date: '2026-03-30', is_overdue: false, permissions: { can_edit: false } },
    ],
    ...over,
  })
  const renderView = () => render(<MemoryRouter><ProjectReviewsView projectId={7} /></MemoryRouter>)

  it('student sees overall performance, full published evaluations, and nothing from unpublished weeks', async () => {
    mockUser = { id: 1, name: 'Stu', role: 'student' }
    svc.reviewService.forProject.mockResolvedValue(data())
    renderView()
    const overall = await screen.findByLabelText('Overall performance')
    expect(overall).toHaveTextContent('1 / 4')
    expect(overall).toHaveTextContent('39 / 50')
    expect(overall).toHaveTextContent('78%')
    const w1 = screen.getByRole('region', { name: 'Week 1' })
    expect(within(w1).getByText('Problem Understanding')).toBeInTheDocument()
    expect(within(w1).getByText('Read IEEE 830')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Week 2' })).getByText('Overdue')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Week 3' })).getByText(/mentor is correcting this evaluation/i)).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Week 4' })).getByText(/not evaluated yet/i)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /evaluate|open/i })).not.toBeInTheDocument()     // students cannot open evaluator pages
  })

  it('mentor sees links to evaluate each week', async () => {
    const d = data()
    d.reviews[1].permissions = { can_edit: true }
    d.reviews[1].visible = true
    d.reviews[1].status = 'draft'
    d.reviews[1].summary = summary({ scored_count: 1, criteria_count: 4, percentage: 20 })
    svc.reviewService.forProject.mockResolvedValue(d)
    renderView()
    expect(await screen.findByRole('link', { name: 'Evaluate' })).toHaveAttribute('href', '/reviews/2')
    expect(screen.getByText(/1\/4 criteria scored · 20% so far/)).toBeInTheDocument()
  })

  it('mentor can sign off the final evaluation when allowed, remarks required', async () => {
    svc.reviewService.forProject.mockResolvedValue(data({ final_evaluation: { signed_off: false, remarks: null, signed_by: null, can_sign_off: true, all_reviews_submitted: true } }))
    svc.reviewService.signoff.mockResolvedValue({})
    renderView()
    await userEvent.click(await screen.findByRole('button', { name: /sign off final evaluation/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/remarks are required/i)
    expect(svc.reviewService.signoff).not.toHaveBeenCalled()
    await userEvent.type(screen.getByLabelText(/final remarks/i), 'Excellent project')
    await userEvent.click(screen.getByRole('button', { name: /sign off final evaluation/i }))
    await waitFor(() => expect(svc.reviewService.signoff).toHaveBeenCalledWith(7, 'Excellent project'))
    await waitFor(() => expect(svc.reviewService.forProject).toHaveBeenCalledTimes(2))
  })

  it('shows the signed-off final evaluation to everyone, and a waiting message otherwise', async () => {
    mockUser = { id: 1, name: 'Stu', role: 'student' }
    svc.reviewService.forProject.mockResolvedValue(data({ final_evaluation: { signed_off: true, remarks: 'Great job', signed_by: 'Mia', can_sign_off: false, all_reviews_submitted: true } }))
    renderView()
    const panel = await screen.findByRole('region', { name: 'Final evaluation' })
    expect(within(panel).getByText('Signed off')).toBeInTheDocument()
    expect(within(panel).getByText('Great job')).toBeInTheDocument()
  })

  it('explains why sign-off is not available yet', async () => {
    svc.reviewService.forProject.mockResolvedValue(data())
    renderView()
    expect(await screen.findByText(/once all four weekly reviews are submitted/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /sign off/i })).not.toBeInTheDocument()
  })
})

describe('evaluation queue', () => {
  const ITEM = { review_id: 11, week_no: 2, status: 'draft', status_label: 'In progress', due_date: '2026-03-02', is_overdue: true, project: { id: 7, title: 'Smart Attendance', batch: 'B1', students: ['Asha K'] } }
  const renderQueue = () => render(<MemoryRouter><EvaluationQueuePage /></MemoryRouter>)
  it('lists pending reviews with an Evaluate link for mentors and filters by week/overdue', async () => {
    svc.reviewService.queue.mockResolvedValue({ items: [ITEM], meta: { page: 1, pages: 1, total: 1 } })
    renderQueue()
    expect(await screen.findByRole('heading', { name: 'Weekly Evaluations' })).toBeInTheDocument()
    expect(screen.getByText(/2026-03-02 · overdue/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /evaluate/i })).toHaveAttribute('href', '/reviews/11')
    await userEvent.selectOptions(screen.getByLabelText(/filter by week/i), '2')
    await waitFor(() => expect(svc.reviewService.queue).toHaveBeenLastCalledWith({ page: 1, week: '2', overdue: undefined }))
    await userEvent.click(screen.getByLabelText(/overdue only/i))
    await waitFor(() => expect(svc.reviewService.queue).toHaveBeenLastCalledWith({ page: 1, week: '2', overdue: 1 }))
  })
  it('is a read-only monitoring view for leads', async () => {
    mockUser = { id: 3, name: 'Lea', role: 'domain_lead' }
    svc.reviewService.queue.mockResolvedValue({ items: [ITEM], meta: { page: 1, pages: 1, total: 1 } })
    renderQueue()
    expect(await screen.findByRole('heading', { name: 'Review Monitoring' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /view/i })).toBeInTheDocument()
  })
})

describe('templates page', () => {
  const T = { id: 1, name: 'Week 1 sample', week_no: 1, total_marks: 100, criteria: [{ name: 'SRS Quality', max_marks: 100 }] }
  it('adds sample templates on request and reports the result', async () => {
    svc.templateService.list.mockResolvedValueOnce([]).mockResolvedValue([T])
    svc.templateService.samples.mockResolvedValue([T, T, T, T])
    render(<TemplatesPage />)
    expect(await screen.findByText(/no templates yet/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /add sample templates/i }))
    expect(await screen.findByText(/4 sample template\(s\) added/i)).toBeInTheDocument()
    expect(await screen.findByText('Week 1 sample')).toBeInTheDocument()
  })

  it('creates a template with its own criteria and total', async () => {
    svc.templateService.create.mockResolvedValue(T)
    render(<TemplatesPage />)
    await userEvent.click(await screen.findByRole('button', { name: /new template/i }))
    const dialog = screen.getByRole('dialog')
    await userEvent.type(within(dialog).getByLabelText(/^name/i), 'Mine')
    await userEvent.selectOptions(within(dialog).getByLabelText(/suggested for/i), '3')
    await userEvent.type(within(dialog).getByLabelText('Template criterion 1 name'), 'Testing')
    await userEvent.type(within(dialog).getByLabelText('Template criterion 1 marks'), '25')
    await userEvent.click(within(dialog).getByRole('button', { name: /add criterion/i }))
    await userEvent.type(within(dialog).getByLabelText('Template criterion 2 name'), 'Docs')
    await userEvent.type(within(dialog).getByLabelText('Template criterion 2 marks'), '15')
    expect(within(dialog).getByText(/total marks:/i)).toHaveTextContent('40')
    await userEvent.click(within(dialog).getByRole('button', { name: /save template/i }))
    await waitFor(() => expect(svc.templateService.create).toHaveBeenCalledWith({ name: 'Mine', week_no: 3, criteria: [{ name: 'Testing', max_marks: '25' }, { name: 'Docs', max_marks: '15' }] }))
  })

  it('confirms before deleting a template', async () => {
    svc.templateService.list.mockResolvedValue([T])
    svc.templateService.remove.mockResolvedValue({})
    render(<TemplatesPage />)
    await userEvent.click(await screen.findByRole('button', { name: /delete week 1 sample/i }))
    expect(svc.templateService.remove).not.toHaveBeenCalled()
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^delete$/i }))
    await waitFor(() => expect(svc.templateService.remove).toHaveBeenCalledWith(1))
  })
})

describe('navigation', () => {
  it.each([
    ['student', '/student', ['Weekly Reviews']], ['mentor', '/mentor', ['Weekly Evaluations', 'Evaluation Templates']],
    ['domain_lead', '/lead', ['Review Monitoring']], ['admin', '/admin', ['Evaluations']],
  ])('%s sees the evaluation menu entries', async (role, path, labels) => {
    mockUser = { id: 1, name: 'U', role }
    localStorage.setItem('plms_access', 'tok')
    api.get.mockImplementation((url) => Promise.resolve(url === '/auth/me'
      ? { data: { data: { id: 1, name: 'U', email: 'u@x.com', role, must_change_password: false } } } : { data: { data: { count: 0 } } }))
    render(<MemoryRouter initialEntries={[path]}><AuthProvider><App /></AuthProvider></MemoryRouter>)
    const nav = await screen.findByRole('navigation', { name: /main navigation/i })
    for (const l of labels) expect(nav).toHaveTextContent(l)
  })
})
