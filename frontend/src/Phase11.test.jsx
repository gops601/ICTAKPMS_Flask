import { render, screen, waitFor, within, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ReviewEditor from './components/ReviewEditor'
import DateRequestsPage from './pages/common/DateRequestsPage'
import { ProjectReviewsView, ReviewPage } from './pages/common/ReviewPages'
import { LeadDashboard } from './pages/common/Dashboards'
import App from './App'
import { AuthProvider } from './context/AuthContext'
import api from './services/api'
import * as svc from './services/adminService'

vi.mock('./pages/common/Dashboards', async () => {
  const React = await import('react')
  const { useAuth } = await import('./context/AuthContext')
  const Stub = () => { const { user } = useAuth(); return React.createElement('h1', null, `Welcome, ${user.name}`) }
  return { AdminDashboard: Stub, LeadDashboard: Stub, MentorDashboard: Stub, StudentDashboard: Stub }
})

let mockUser = { id: 4, name: 'Mia Mentor', role: 'mentor' }
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
    reviewService: { get: vi.fn(), save: vi.fn(), submit: vi.fn(), reopen: vi.fn(), revisions: vi.fn(), applyTemplate: vi.fn(), forProject: vi.fn() },
    reviewDateService: { list: vi.fn(), create: vi.fn(), decide: vi.fn(), cancel: vi.fn(), history: vi.fn() },
    templateService: { list: vi.fn().mockResolvedValue([]) },
    batchService: { list: vi.fn() },
    notificationService: { unreadCount: vi.fn().mockResolvedValue(0), list: vi.fn(), markRead: vi.fn(), readAll: vi.fn() },
  }
})

const review = (over = {}) => ({
  id: 11, project_id: 7, week_no: 2, due_date: '2026-03-16', is_overdue: false, status: 'draft', status_label: 'In progress', version: 3, visible: true,
  review_date: null, mentor: 'Mia Mentor', remarks: null, strengths: null, improvements: null, recommendations: null,
  criteria: [{ id: 1, name: 'Design', max_marks: 40, marks_obtained: 30, remarks: null }],
  summary: { total_obtained: 30, total_max: 40, percentage: 75, criteria_count: 1, scored_count: 1 }, student_remarks: [], revert_note: null, date_request: null,
  permissions: { can_edit: true, can_submit: true, can_reopen: false, can_request_date_change: false, can_decide_date_request: false, reason: null }, ...over,
})
const PENDING = { id: 21, review_id: 11, week_no: 2, status: 'pending', old_date: '2026-03-20', new_date: '2026-03-27', due_date: '2026-03-16', reason: 'Student is on leave',
  requested_by: 'Mia Mentor', requested_at: '2026-03-10T08:00:00', decided_by: null, decided_at: null, decision_note: null,
  project: { id: 7, title: 'Smart Attendance', batch: { id: 5, code: 'B1' }, students: ['Asha K'] } }

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  mockUser = { id: 4, name: 'Mia Mentor', role: 'mentor' }
  svc.templateService.list.mockResolvedValue([])
  svc.reviewService.revisions.mockResolvedValue([])
  svc.batchService.list.mockResolvedValue({ items: [{ id: 5, code: 'B1', name: 'Batch One' }], meta: {} })
  svc.notificationService.unreadCount.mockResolvedValue(0)
})

describe('mentor: review date field', () => {
  it('lets the mentor assign the date the first time, with a hint that later changes need approval', async () => {
    svc.reviewService.save.mockResolvedValue(review({ version: 4, review_date: '2026-03-20' }))
    render(<ReviewEditor review={review()} onChange={vi.fn()} />)
    const input = screen.getByLabelText('Review date', { selector: 'input' })
    expect(input).toBeEnabled()
    expect(screen.getByText(/changing it needs your domain lead's approval/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /request date change/i })).not.toBeInTheDocument()
    fireEvent.change(input, { target: { value: '2026-03-20' } })
    await userEvent.click(screen.getByRole('button', { name: /save draft/i }))
    await waitFor(() => expect(svc.reviewService.save).toHaveBeenCalled())
    expect(svc.reviewService.save.mock.calls[0][1].review_date).toBe('2026-03-20')
  })

  it('locks a scheduled date and offers "Request date change" instead', async () => {
    svc.reviewService.save.mockResolvedValue(review())
    render(<ReviewEditor review={review({ review_date: '2026-03-20', permissions: { can_edit: true, can_request_date_change: true } })} onChange={vi.fn()} />)
    expect(screen.getByLabelText('Review date', { selector: 'input' })).toBeDisabled()
    expect(screen.getByLabelText('Review date', { selector: 'input' })).toHaveValue('2026-03-20')
    expect(screen.getByText(/scheduled – changes need your domain lead's approval/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /save draft/i }))
    await waitFor(() => expect(svc.reviewService.save).toHaveBeenCalled())
    expect(svc.reviewService.save.mock.calls[0][1].review_date).toBe('2026-03-20')      // unchanged date is still sent, so saving keeps working
  })

  it('validates the request locally, sends it, and refreshes the review', async () => {
    svc.reviewDateService.create.mockResolvedValue(PENDING)
    const onChange = vi.fn()
    svc.reviewService.get.mockResolvedValue(review({ review_date: '2026-03-20', date_request: PENDING }))
    render(<ReviewEditor review={review({ review_date: '2026-03-20', permissions: { can_edit: true, can_request_date_change: true } })} onChange={onChange} />)
    await userEvent.click(screen.getByRole('button', { name: /request date change/i }))
    const dialog = screen.getByRole('dialog', { name: /request a review date change/i })
    expect(within(dialog).getByText('2026-03-20')).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('button', { name: /send for approval/i }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(/choose the new date/i)
    fireEvent.change(within(dialog).getByLabelText(/new review date/i), { target: { value: '2026-03-27' } })
    await userEvent.click(within(dialog).getByRole('button', { name: /send for approval/i }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(/at least 5 characters/i)
    expect(svc.reviewDateService.create).not.toHaveBeenCalled()
    await userEvent.type(within(dialog).getByLabelText(/reason/i), 'Student is on leave')
    await userEvent.click(within(dialog).getByRole('button', { name: /send for approval/i }))
    await waitFor(() => expect(svc.reviewDateService.create).toHaveBeenCalledWith(11, '2026-03-27', 'Student is on leave'))
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ date_request: PENDING })))
    expect(screen.getByText(/request sent to your domain lead/i)).toBeInTheDocument()
  })

  it('shows the server message when the request is refused', async () => {
    svc.reviewDateService.create.mockRejectedValue({ response: { status: 409, data: { message: 'A date-change request for this review is already awaiting approval' } } })
    render(<ReviewEditor review={review({ review_date: '2026-03-20', permissions: { can_edit: true, can_request_date_change: true } })} onChange={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /request date change/i }))
    const dialog = screen.getByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText(/new review date/i), { target: { value: '2026-03-27' } })
    await userEvent.type(within(dialog).getByLabelText(/reason/i), 'Clash with exams')
    await userEvent.click(within(dialog).getByRole('button', { name: /send for approval/i }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(/already awaiting approval/i)
  })

  it('shows a pending request instead of the request button, and lets the mentor withdraw it', async () => {
    svc.reviewDateService.cancel.mockResolvedValue({ ...PENDING, status: 'cancelled' })
    svc.reviewService.get.mockResolvedValue(review({ review_date: '2026-03-20' }))
    const onChange = vi.fn()
    render(<ReviewEditor review={review({ review_date: '2026-03-20', date_request: PENDING, permissions: { can_edit: true, can_request_date_change: false } })} onChange={onChange} />)
    expect(screen.getByText(/waiting for domain lead approval/i)).toHaveTextContent('2026-03-27')
    expect(screen.getByText(/student is on leave/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /request date change/i })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /withdraw request/i }))
    await waitFor(() => expect(svc.reviewDateService.cancel).toHaveBeenCalledWith(21))
    await waitFor(() => expect(onChange).toHaveBeenCalled())
  })
})

describe('review pages', () => {
  const renderPage = () => render(<MemoryRouter initialEntries={['/reviews/11']}><Routes><Route path="/reviews/:reviewId" element={<ReviewPage />} /></Routes></MemoryRouter>)

  it('the Domain Lead sees the pending request on the review with a link to the approvals page', async () => {
    mockUser = { id: 3, name: 'Lea Lead', role: 'domain_lead' }
    svc.reviewService.get.mockResolvedValue(review({ review_date: '2026-03-20', date_request: PENDING, permissions: { can_edit: false, can_reopen: false } }))
    renderPage()
    expect(await screen.findByText(/asked to move this review from 2026-03-20/i)).toHaveTextContent('2026-03-27')
    expect(screen.getByRole('link', { name: /review the request/i })).toHaveAttribute('href', '/lead/date-requests')
    expect(screen.getByText(/Review date 2026-03-20/)).toBeInTheDocument()
  })

  it('students see the scheduled date of a review that is not published yet', async () => {
    mockUser = { id: 9, name: 'Stu', role: 'student' }
    const base = { project_id: 7, due_date: '2026-03-16', is_overdue: false, permissions: { can_edit: false } }
    svc.reviewService.forProject.mockResolvedValue({
      project: { id: 7, title: 'P', stage: 'implementation', stage_label: 'Implementation' },
      overall: { reviews_submitted: 0, reviews_total: 4, total_obtained: 0, total_max: 0, percentage: 0, average_percentage: 0, reviews: [] },
      final_evaluation: { signed_off: false, can_sign_off: false, all_reviews_submitted: false },
      reviews: [{ ...base, id: 1, week_no: 1, status: 'pending', status_label: 'Pending', visible: false, review_date: '2026-03-20' },
        { ...base, id: 2, week_no: 2, status: 'pending', status_label: 'Pending', visible: false, review_date: null }],
    })
    render(<MemoryRouter><ProjectReviewsView projectId={7} /></MemoryRouter>)
    const w1 = await screen.findByRole('region', { name: 'Week 1' })
    expect(within(w1).getByText('Scheduled 2026-03-20')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Week 2' })).queryByText(/scheduled/i)).not.toBeInTheDocument()
  })
})

describe('Date Approvals page', () => {
  const OTHER = { ...PENDING, id: 22, reason: 'Exam clash', status: 'approved', decided_by: 'Lea Lead', decision_note: 'Fine', week_no: 1, project: { ...PENDING.project, title: 'Beta' } }
  const LIST = { items: [PENDING, OTHER], meta: { page: 1, pages: 1, total: 2 } }
  const renderPage = () => render(<MemoryRouter><DateRequestsPage /></MemoryRouter>)
  beforeEach(() => { mockUser = { id: 3, name: 'Lea Lead', role: 'domain_lead' }; svc.reviewDateService.list.mockResolvedValue(LIST) })

  it('opens on the pending requests with old → new date, due date, reason and who asked', async () => {
    renderPage()
    expect(await screen.findByRole('heading', { name: 'Review Date Approvals' })).toBeInTheDocument()
    expect(svc.reviewDateService.list).toHaveBeenCalledWith({ page: 1, status: 'pending', batch_id: undefined })
    expect(await screen.findByRole('link', { name: 'Smart Attendance' })).toHaveAttribute('href', '/reviews/11')
    expect(screen.getByText('Student is on leave')).toBeInTheDocument()
    expect(screen.getAllByText(/by Mia Mentor/)).toHaveLength(2)                // one line per request row
    expect(screen.getByText(/“Fine” – Lea Lead/)).toBeInTheDocument()
  })

  it('approving sends the decision and confirms to the lead', async () => {
    svc.reviewDateService.decide.mockResolvedValue({ ...PENDING, status: 'approved' })
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: /approve date change for smart attendance week 2/i }))
    const dialog = screen.getByRole('dialog', { name: /approve date change/i })
    expect(within(dialog).getByText(/mentor's reason: student is on leave/i)).toBeInTheDocument()
    await userEvent.type(within(dialog).getByLabelText(/note \(optional\)/i), 'Agreed')
    await userEvent.click(within(dialog).getByRole('button', { name: /^approve$/i }))
    await waitFor(() => expect(svc.reviewDateService.decide).toHaveBeenCalledWith(21, 'approve', 'Agreed'))
    expect(await screen.findByText(/the mentor and student were notified/i)).toBeInTheDocument()
    await waitFor(() => expect(svc.reviewDateService.list).toHaveBeenCalledTimes(2))        // list reloads
  })

  it('rejecting requires a reason before anything is sent', async () => {
    svc.reviewDateService.decide.mockResolvedValue({ ...PENDING, status: 'rejected' })
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: /reject date change for smart attendance week 2/i }))
    const dialog = screen.getByRole('dialog', { name: /reject date change/i })
    await userEvent.click(within(dialog).getByRole('button', { name: /^reject$/i }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(/give a reason for rejecting/i)
    expect(svc.reviewDateService.decide).not.toHaveBeenCalled()
    await userEvent.type(within(dialog).getByLabelText(/reason for rejecting/i), 'Keep the original date')
    await userEvent.click(within(dialog).getByRole('button', { name: /^reject$/i }))
    await waitFor(() => expect(svc.reviewDateService.decide).toHaveBeenCalledWith(21, 'reject', 'Keep the original date'))
  })

  it('shows server errors inside the dialog (e.g. already decided)', async () => {
    svc.reviewDateService.decide.mockRejectedValue({ response: { status: 409, data: { message: 'This request was already approved' } } })
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: /approve date change/i }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^approve$/i }))
    expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveTextContent(/already approved/)
  })

  it('has no action buttons on decided requests and filters by status and batch', async () => {
    renderPage()
    await screen.findByText('Beta')
    expect(screen.getAllByRole('button', { name: /approve date change/i })).toHaveLength(1)    // only the pending one
    await userEvent.selectOptions(screen.getByLabelText(/filter by status/i), 'approved')
    await waitFor(() => expect(svc.reviewDateService.list).toHaveBeenLastCalledWith({ page: 1, status: 'approved', batch_id: undefined }))
    const batch = screen.getByLabelText('Filter by batch')
    await waitFor(() => expect(within(batch).getAllByRole('option')).toHaveLength(2))
    await userEvent.selectOptions(batch, '5')
    await waitFor(() => expect(svc.reviewDateService.list).toHaveBeenLastCalledWith({ page: 1, status: 'approved', batch_id: '5' }))
  })

  it('shows a friendly empty state', async () => {
    svc.reviewDateService.list.mockResolvedValue({ items: [], meta: { page: 1, pages: 1, total: 0 } })
    renderPage()
    expect(await screen.findByText(/no date changes are waiting for approval/i)).toBeInTheDocument()
  })

  it('mentors see their own requests, can withdraw pending ones, and cannot approve', async () => {
    mockUser = { id: 4, name: 'Mia Mentor', role: 'mentor' }
    svc.reviewDateService.cancel.mockResolvedValue({})
    renderPage()
    expect(await screen.findByRole('heading', { name: 'My Date Requests' })).toBeInTheDocument()
    expect(svc.reviewDateService.list).toHaveBeenCalledWith({ page: 1, status: undefined, batch_id: undefined })
    expect(screen.queryByRole('button', { name: /approve date change/i })).not.toBeInTheDocument()
    await userEvent.click(await screen.findByRole('button', { name: 'Withdraw' }))
    await waitFor(() => expect(svc.reviewDateService.cancel).toHaveBeenCalledWith(21))
    expect(await screen.findByText(/request withdrawn/i)).toBeInTheDocument()
  })
})

describe('navigation', () => {
  it.each([['domain_lead', '/lead', 'Date Approvals'], ['admin', '/admin', 'Date Approvals'], ['mentor', '/mentor', 'Date Requests']])(
    '%s sees the date menu entry', async (role, path, label) => {
      mockUser = { id: 1, name: 'U', role }
      localStorage.setItem('plms_access', 'tok')
      api.get.mockImplementation((url) => Promise.resolve(url === '/auth/me'
        ? { data: { data: { id: 1, name: 'U', email: 'u@x.com', role, must_change_password: false } } } : { data: { data: { count: 0 } } }))
      render(<MemoryRouter initialEntries={[path]}><AuthProvider><App /></AuthProvider></MemoryRouter>)
      expect(await screen.findByRole('navigation', { name: /main navigation/i })).toHaveTextContent(label)
    })

  it('students do not get a date entry', async () => {
    mockUser = { id: 2, name: 'Stu', role: 'student' }
    localStorage.setItem('plms_access', 'tok')
    api.get.mockImplementation((url) => Promise.resolve(url === '/auth/me'
      ? { data: { data: { id: 2, name: 'Stu', email: 's@x.com', role: 'student', must_change_password: false } } } : { data: { data: { count: 0 } } }))
    render(<MemoryRouter initialEntries={['/student']}><AuthProvider><App /></AuthProvider></MemoryRouter>)
    const nav = await screen.findByRole('navigation', { name: /main navigation/i })
    expect(nav).not.toHaveTextContent(/date approvals|date requests/i)
  })
})

void LeadDashboard
