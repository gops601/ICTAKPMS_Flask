import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ReviewEditor from './components/ReviewEditor'
import ReviewDetail from './components/ReviewDetail'
import { ReviewPage } from './pages/common/ReviewPages'
import ReportsPage from './pages/common/ReportsPage'
import BatchDetail from './pages/common/BatchDetail'
import BatchList from './pages/admin/BatchList'
import AuthLayout from './layouts/AuthLayout'
import WelcomeBanner from './components/WelcomeBanner'
import { AiNetworkHero, EmptyState, HeroIllustration, LogoMark } from './components/illustrations'
import * as svc from './services/adminService'

let mockUser = { id: 4, name: 'Mia Mentor', role: 'mentor' }
vi.mock('./context/AuthContext', async () => {
  const actual = await vi.importActual('./context/AuthContext')
  return { ...actual, useAuth: () => ({ user: mockUser }) }
})
vi.mock('./hooks/useBasePath', () => ({ default: () => '/lead' }))
vi.mock('./services/adminService', async () => {
  const actual = await vi.importActual('./services/adminService')
  return {
    ...actual,
    downloadFile: vi.fn(),
    reviewService: { get: vi.fn(), save: vi.fn(), submit: vi.fn(), reopen: vi.fn(), revisions: vi.fn(), applyTemplate: vi.fn() },
    templateService: { list: vi.fn().mockResolvedValue([]) },
    reportService: { list: vi.fn(), get: vi.fn(), download: vi.fn(), batchDetailed: vi.fn() },
    batchService: { list: vi.fn(), get: vi.fn(), setStatus: vi.fn() },
    studentService: { list: vi.fn() },
    projectService: { list: vi.fn() },
    batchMentorService: { list: vi.fn() },
    userService: { mentors: vi.fn() },
    ouService: { list: vi.fn() },
    domainService: { list: vi.fn() },
  }
})

const crit = (id, name, max, got = null) => ({ id, name, max_marks: max, marks_obtained: got, remarks: null })
const REMARKS = [{ student_id: 1, name: 'Asha K', registration_no: 'R1', remarks: 'Led the design', marks_obtained: 8 }, { student_id: 2, name: 'Ben J', registration_no: 'R2', remarks: '', marks_obtained: null }]
const review = (over = {}) => ({
  id: 11, project_id: 7, week_no: 1, due_date: '2026-03-09', is_overdue: false, status: 'draft', status_label: 'In progress', version: 2, visible: true,
  review_date: null, mentor: 'Mia Mentor', remarks: 'Solid', strengths: null, improvements: null, recommendations: null,
  criteria: [crit(1, 'Design', 40, 30)], summary: { total_obtained: 30, total_max: 40, percentage: 75, criteria_count: 1, scored_count: 1 },
  student_remarks: REMARKS, revert_note: null, permissions: { can_edit: true, can_submit: true, can_reopen: false, reason: null }, ...over,
})
const submitted = (over = {}) => review({ status: 'submitted', status_label: 'Submitted',
  permissions: { can_edit: false, can_submit: false, can_reopen: true, reason: 'Submitted reviews are read-only. Reopen to correct them.' }, ...over })

beforeEach(() => {
  vi.clearAllMocks()
  mockUser = { id: 4, name: 'Mia Mentor', role: 'mentor' }
  svc.templateService.list.mockResolvedValue([])
  svc.reviewService.revisions.mockResolvedValue([])
})

describe('remarks for every student (mentor)', () => {
  it('shows a remark box for each student and sends them with the draft', async () => {
    svc.reviewService.save.mockResolvedValue(review({ version: 3 }))
    render(<ReviewEditor review={review()} onChange={vi.fn()} />)
    const region = screen.getByLabelText('Remarks for each student')
    expect(within(region).getByText(/never any marks/i)).toBeInTheDocument()
    expect(within(region).getByLabelText('Individual marks for Asha K')).toHaveValue(8)
    expect(within(region).getByLabelText('Remarks for Asha K')).toHaveValue('Led the design')
    await userEvent.type(within(region).getByLabelText('Remarks for Ben J'), 'Needs to commit more code')
    await userEvent.click(screen.getByRole('button', { name: /save draft/i }))
    await waitFor(() => expect(svc.reviewService.save).toHaveBeenCalled())
    expect(svc.reviewService.save.mock.calls[0][1].student_remarks).toEqual([
      { student_id: 1, remarks: 'Led the design', marks_obtained: 8 }, { student_id: 2, remarks: 'Needs to commit more code', marks_obtained: null }])
  })

  it('submits the individual remarks in the same call as the scores', async () => {
    svc.reviewService.submit.mockResolvedValue(submitted())
    render(<ReviewEditor review={review()} onChange={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /submit evaluation/i }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^submit$/i }))
    await waitFor(() => expect(svc.reviewService.submit).toHaveBeenCalled())
    expect(svc.reviewService.submit.mock.calls[0][1].student_remarks).toHaveLength(2)
  })

  it('shows server errors for a single remark row', async () => {
    svc.reviewService.save.mockRejectedValue({ response: { status: 422, data: { message: 'Validation failed', errors: { 'student_remarks.1': 'Remarks are too long (max 2000 characters)' } } } })
    render(<ReviewEditor review={review()} onChange={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /save draft/i }))
    expect((await screen.findAllByText(/remarks are too long/i)).length).toBeGreaterThan(0)
  })

  it('has no per-student section when the API sends none', () => {
    render(<ReviewEditor review={review({ student_remarks: undefined })} onChange={vi.fn()} />)
    expect(screen.queryByLabelText('Remarks for each student')).not.toBeInTheDocument()
  })

  it('read-only detail shows each non-empty remark with the student name', () => {
    render(<ReviewDetail review={submitted()} />)
    const box = screen.getByRole('region', { name: 'Individual evaluation' })
    expect(within(box).getByText('Asha K')).toBeInTheDocument()
    expect(within(box).getByText(/Led the design/)).toBeInTheDocument()
    expect(within(box).queryByText('Ben J:')).not.toBeInTheDocument()          // empty remarks are not shown
  })

  it('a student only receives (and sees) their own remark', () => {
    // students receive summary: null and no marks anywhere
    render(<ReviewDetail review={submitted({ summary: null, student_remarks: [{ student_id: 1, name: 'Asha K', registration_no: 'R1', remarks: 'Led the design' }],
      criteria: [{ id: 1, name: 'Design', remarks: 'Clean structure' }] })} />)
    expect(screen.getByText(/Led the design/)).toBeInTheDocument()
    expect(screen.getByText(/Clean structure/)).toBeInTheDocument()
    expect(screen.queryByText(/Ben J/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Obtained|Max|%/)).not.toBeInTheDocument()
  })

  it('hides the section when there are no remarks', () => {
    render(<ReviewDetail review={submitted({ student_remarks: [{ ...REMARKS[1] }] })} />)
    expect(screen.queryByRole('region', { name: 'Remarks for students' })).not.toBeInTheDocument()
  })
})

describe('only mentors score; Domain Leads revert to the mentor', () => {
  const renderPage = () => render(<MemoryRouter initialEntries={['/reviews/11']}><Routes><Route path="/reviews/:reviewId" element={<ReviewPage />} /></Routes></MemoryRouter>)

  it('a Domain Lead sees the score read-only with a "Revert to mentor" action and the mentors-only note', async () => {
    mockUser = { id: 3, name: 'Lea Lead', role: 'domain_lead' }
    svc.reviewService.get.mockResolvedValue(submitted())
    renderPage()
    expect(await screen.findByText('Design')).toBeInTheDocument()
    expect(screen.getByText(/only the assigned mentor can give or change scores/i)).toBeInTheDocument()
    expect(screen.getByText(/revert it to the mentor with a reason/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /submit evaluation|save draft/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /reopen to correct/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /revert to mentor/i })).toBeInTheDocument()
  })

  it('reverting requires a reason, explains the effect and calls the API', async () => {
    mockUser = { id: 3, name: 'Lea Lead', role: 'domain_lead' }
    svc.reviewService.get.mockResolvedValue(submitted())
    svc.reviewService.reopen.mockResolvedValue(review({ status: 'reopened', status_label: 'Under revision', permissions: { can_edit: false, can_reopen: false } }))
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: /revert to mentor/i }))
    const dialog = screen.getByRole('dialog', { name: /revert score to mentor/i })
    expect(within(dialog).getByText(/goes back to the mentor, who is notified with your reason/i)).toBeInTheDocument()
    await userEvent.type(within(dialog).getByLabelText(/reason/i), 'Marks look too generous')
    await userEvent.click(within(dialog).getByRole('button', { name: /^revert$/i }))
    await waitFor(() => expect(svc.reviewService.reopen).toHaveBeenCalledWith('11', 'Marks look too generous'))
    expect(await screen.findByText('Under revision')).toBeInTheDocument()
  })

  it('shows the server message when the revert is refused', async () => {
    mockUser = { id: 3, name: 'Lea Lead', role: 'domain_lead' }
    svc.reviewService.get.mockResolvedValue(submitted())
    svc.reviewService.reopen.mockRejectedValue({ response: { status: 422, data: { message: 'A reason (at least 5 characters) is required to reopen a review' } } })
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: /revert to mentor/i }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^revert$/i }))
    expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveTextContent(/at least 5 characters/)
  })

  it('the mentor sees who sent the score back and why, and can edit it again', async () => {
    svc.reviewService.get.mockResolvedValue(review({ status: 'reopened', status_label: 'Under revision',
      revert_note: { reason: 'Marks look too generous', by: 'Lea Lead', by_role: 'domain_lead', at: '2026-03-10T08:00:00' } }))
    renderPage()
    expect(await screen.findByText(/sent back for updating by lea lead \(domain lead\)/i)).toBeInTheDocument()
    expect(screen.getByText(/marks look too generous/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /submit evaluation/i })).toBeInTheDocument()
  })

  it('an administrator cannot score either and keeps the original "Reopen" wording', async () => {
    mockUser = { id: 1, name: 'Ada Admin', role: 'admin' }
    svc.reviewService.get.mockResolvedValue(submitted())
    renderPage()
    expect(await screen.findByText(/only the assigned mentor can give or change scores/i)).toBeInTheDocument()
    expect(screen.queryByText(/revert it to the mentor/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reopen to correct/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /submit evaluation/i })).not.toBeInTheDocument()
  })

  it('the mentors themselves see no "only mentors" notice', async () => {
    svc.reviewService.get.mockResolvedValue(review())
    renderPage()
    await screen.findByRole('button', { name: /submit evaluation/i })
    expect(screen.queryByText(/only the assigned mentor can give/i)).not.toBeInTheDocument()
  })
})

describe('batch detailed report downloads', () => {
  const BATCHES = { items: [{ id: 5, code: 'B1', name: 'Batch One', ou: { name: 'Retail OU' }, domain: { name: 'AI & ML' }, student_count: 4, status: 'active' }], meta: { page: 1, pages: 1, total: 1 } }
  beforeEach(() => {
    svc.batchService.list.mockResolvedValue(BATCHES)
    svc.reportService.list.mockResolvedValue([{ type: 'batch', title: 'Batch-wise report', filters: ['batch_id'] }])
    svc.reportService.get.mockResolvedValue({ type: 'batch', title: 'Batch-wise report', generated_at: '2026-03-10T08:00:00', columns: [{ key: 'code', label: 'Batch code' }], rows: [], meta: { page: 1, pages: 1, total: 0 } })
    svc.reportService.batchDetailed.mockResolvedValue()
    svc.domainService.list.mockResolvedValue([])
    svc.ouService.list.mockResolvedValue([])
  })

  it('Reports page: pick a batch, then download the Excel workbook or a single CSV sheet', async () => {
    mockUser = { id: 1, name: 'Ada Admin', role: 'admin' }
    render(<MemoryRouter><ReportsPage /></MemoryRouter>)
    const card = await screen.findByRole('region', { name: 'Batch detailed report' })
    expect(within(card).getByRole('button', { name: /download excel/i })).toBeDisabled()
    await waitFor(() => expect(within(card).getByRole('option', { name: 'B1 – Batch One' })).toBeInTheDocument())
    await userEvent.selectOptions(within(card).getByLabelText('Batch for detailed report'), '5')
    await userEvent.click(within(card).getByRole('button', { name: /download excel \(all sheets\)/i }))
    expect(svc.reportService.batchDetailed).toHaveBeenLastCalledWith('5', 'xlsx', undefined)
    await userEvent.click(within(card).getByRole('button', { name: /CSV · Weekly scores/ }))
    expect(svc.reportService.batchDetailed).toHaveBeenLastCalledWith('5', 'csv', 'weekly')
    await userEvent.click(within(card).getByRole('button', { name: /CSV · Students/ }))
    expect(svc.reportService.batchDetailed).toHaveBeenLastCalledWith('5', 'csv', 'students')
  })

  it('is also available to Domain Leads, but not to mentors', async () => {
    mockUser = { id: 3, name: 'Lea Lead', role: 'domain_lead' }
    const { unmount } = render(<MemoryRouter><ReportsPage /></MemoryRouter>)
    expect(await screen.findByRole('region', { name: 'Batch detailed report' })).toBeInTheDocument()
    unmount()
    mockUser = { id: 4, name: 'Mia Mentor', role: 'mentor' }
    render(<MemoryRouter><ReportsPage title="Project Reports" /></MemoryRouter>)
    await screen.findByRole('heading', { name: 'Project Reports' })
    expect(screen.queryByRole('region', { name: 'Batch detailed report' })).not.toBeInTheDocument()
  })

  it('shows a readable error when the download fails', async () => {
    mockUser = { id: 1, name: 'Ada Admin', role: 'admin' }
    svc.reportService.batchDetailed.mockRejectedValue({ response: { status: 404, data: { message: 'Batch not found' } } })
    render(<MemoryRouter><ReportsPage /></MemoryRouter>)
    const card = await screen.findByRole('region', { name: 'Batch detailed report' })
    await waitFor(() => expect(within(card).getByRole('option', { name: /B1/ })).toBeInTheDocument())
    await userEvent.selectOptions(within(card).getByLabelText('Batch for detailed report'), '5')
    await userEvent.click(within(card).getByRole('button', { name: /download excel/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Batch not found')
  })

  it('batch page: Domain Lead / admin get a "Detailed report" button, a mentor does not', async () => {
    svc.batchService.get.mockResolvedValue({ id: 5, code: 'B1', name: 'Batch One', status: 'active', student_count: 4, details: {}, ou: { name: 'Retail OU' }, domain: { id: 2, name: 'AI & ML' } })
    svc.studentService.list.mockResolvedValue({ items: [], meta: {} })
    mockUser = { id: 3, name: 'Lea Lead', role: 'domain_lead' }
    const view = () => render(<MemoryRouter initialEntries={['/lead/batches/5']}><Routes><Route path="/lead/batches/:id" element={<BatchDetail />} /></Routes></MemoryRouter>)
    const { unmount } = view()
    await userEvent.click(await screen.findByRole('button', { name: /detailed report/i }))
    expect(svc.reportService.batchDetailed).toHaveBeenCalledWith(5)
    unmount()
    mockUser = { id: 4, name: 'Mia Mentor', role: 'mentor' }
    view()
    await screen.findByText('B1 – Batch One')
    expect(screen.queryByRole('button', { name: /detailed report/i })).not.toBeInTheDocument()
  })

  it('admin batch list has a per-batch report button', async () => {
    mockUser = { id: 1, name: 'Ada Admin', role: 'admin' }
    svc.ouService.list.mockResolvedValue([])
    render(<MemoryRouter><BatchList /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button', { name: 'Download detailed report for B1' }))
    expect(svc.reportService.batchDetailed).toHaveBeenCalledWith(5)
  })
})

describe('branding and illustrations', () => {
  it('sign-in page shows the illustration, the feature list and the ICTAKPMS name', () => {
    render(<AuthLayout title="Sign in"><p>form</p></AuthLayout>)
    expect(screen.getByRole('img', { name: /illustration of an AI neural network/i })).toBeInTheDocument()
    expect(screen.getAllByRole('img', { name: 'ICTAKPMS logo' }).length).toBeGreaterThan(0)
    expect(screen.getByText(/srs submission, review and approval/i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('the illustration components render accessible, self-contained SVGs', () => {
    const { container } = render(<><LogoMark /><HeroIllustration /><AiNetworkHero /><EmptyState title="Nothing yet">Add something to get started.</EmptyState></>)
    expect(container.querySelectorAll("svg").length).toBe(5) // logo, 2 heroes, empty-state art, AI spark
    expect(container.querySelector('img')).toBeNull()                            // no external image requests
    expect(screen.getByText('Nothing yet')).toBeInTheDocument()
    expect(screen.getByText('Add something to get started.')).toBeInTheDocument()
  })

  it.each([['admin', /institution at a glance/i], ['domain_lead', /your domain is progressing/i], ['mentor', /needs your attention/i], ['student', /where your project stands/i]])(
    'welcome banner greets the %s by first name with a role message', (role, message) => {
      mockUser = { id: 1, name: 'Priya Nair', role }
      render(<WelcomeBanner />)
      expect(screen.getByRole('heading', { name: /^Good (morning|afternoon|evening), Priya!$/ })).toBeInTheDocument()
      expect(screen.getByText(message)).toBeInTheDocument()
    })
})
