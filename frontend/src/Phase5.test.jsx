import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SrsPanel from './components/SrsPanel'
import GithubPanel from './components/GithubPanel'
import { SrsQueuePage } from './pages/common/SrsPages'
import App from './App'
import { AuthProvider } from './context/AuthContext'
import api from './services/api'
import * as svc from './services/adminService'

let mockUser = { id: 1, name: 'Stu', role: 'student' }
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
    srsService: { get: vi.fn(), submit: vi.fn(), review: vi.fn(), queue: vi.fn(), download: vi.fn() },
    githubService: { get: vi.fn(), set: vi.fn() },
    notificationService: { unreadCount: vi.fn().mockResolvedValue(0), list: vi.fn(), markRead: vi.fn(), readAll: vi.fn() },
  }
})

const sub = (over = {}) => ({
  id: 11, version: 1, status: 'submitted', description: 'First draft', submitted_at: '2026-03-03T09:00:00',
  file: { name: 'srs.pdf', size_bytes: 2048, mime_type: 'application/pdf' }, history: [], ...over,
})
const summary = (over = {}) => ({
  project_id: 7, title: 'Smart Attendance', stage: 'srs_preparation', status: 'not_submitted', status_label: 'Not Submitted',
  can_submit: true, implementation_unlocked: false, submissions: [], ...over,
})

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  mockUser = { id: 1, name: 'Stu', role: 'student' }
  svc.notificationService.unreadCount.mockResolvedValue(0)
})

const pdf = new File(['%PDF-1.4'], 'srs.pdf', { type: 'application/pdf' })

describe('SRS panel – student', () => {
  it('shows the Not Submitted status and a locked implementation', async () => {
    svc.srsService.get.mockResolvedValue(summary())
    render(<SrsPanel projectId={7} />)
    expect(await screen.findByText('Not Submitted')).toBeInTheDocument()
    expect(screen.getByText(/implementation locked until the srs is approved/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /submit srs/i })).toBeInTheDocument()
  })

  it('validates the file client-side (type and presence) before calling the API', async () => {
    svc.srsService.get.mockResolvedValue(summary())
    render(<SrsPanel projectId={7} />)
    await userEvent.click(await screen.findByRole('button', { name: /submit srs/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/choose a pdf or docx/i)
    fireEvent.change(screen.getByLabelText(/srs document/i), { target: { files: [new File(['x'], 'virus.exe')] } })
    expect(await screen.findByText(/only pdf or docx/i)).toBeInTheDocument()
    expect(svc.srsService.submit).not.toHaveBeenCalled()
  })

  it('submits the SRS with a description and shows the new submitted state', async () => {
    svc.srsService.get.mockResolvedValue(summary())
    svc.srsService.submit.mockResolvedValue(summary({ status: 'submitted', status_label: 'Submitted', can_submit: false, submissions: [sub()] }))
    render(<SrsPanel projectId={7} />)
    await userEvent.upload(await screen.findByLabelText(/srs document/i), pdf)
    await userEvent.type(screen.getByLabelText(/description/i), 'First draft')
    await userEvent.click(screen.getByRole('button', { name: /submit srs/i }))
    await waitFor(() => expect(svc.srsService.submit).toHaveBeenCalledWith(7, pdf, 'First draft'))
    expect(await screen.findByText(/your mentor has been notified/i)).toBeInTheDocument()
    expect(screen.getByRole('listitem', { name: 'SRS version 1' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /submit srs/i })).not.toBeInTheDocument()
    expect(screen.getByText(/with your mentor for review/i)).toBeInTheDocument()
  })

  it('shows mentor comments, version history and invites a revision when changes are requested', async () => {
    svc.srsService.get.mockResolvedValue(summary({
      stage: 'srs_changes_requested', status: 'changes_requested', status_label: 'Changes Requested', can_submit: true,
      submissions: [sub({ id: 12, version: 2, status: 'submitted', description: 'v2' }),
        sub({ id: 11, version: 1, status: 'changes_requested', history: [
          { id: 1, decision: 'changes_requested', remarks: 'Add use cases', reviewer: 'Mia Mentor', at: '2026-03-04T10:00:00' }] })],
    }))
    render(<SrsPanel projectId={7} />)
    expect(await screen.findByText(/asked for changes/i)).toBeInTheDocument()
    const v1 = screen.getByRole('listitem', { name: 'SRS version 1' })
    expect(within(v1).getByText(/“Add use cases”/)).toBeInTheDocument()
    expect(within(v1).getByText(/Mia Mentor/)).toBeInTheDocument()
    expect(screen.getByRole('listitem', { name: 'SRS version 2' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /submit srs/i })).toBeInTheDocument()
  })

  it('shows the server rejection reason', async () => {
    svc.srsService.get.mockResolvedValue(summary())
    svc.srsService.submit.mockRejectedValue({ response: { status: 422, data: { message: 'The file content does not match its .pdf extension' } } })
    render(<SrsPanel projectId={7} />)
    await userEvent.upload(await screen.findByLabelText(/srs document/i), pdf)
    await userEvent.click(screen.getByRole('button', { name: /submit srs/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/does not match its \.pdf extension/)
  })

  it('shows unlocked implementation after approval and hides the submit form', async () => {
    svc.srsService.get.mockResolvedValue(summary({ status: 'approved', status_label: 'Approved', can_submit: false, implementation_unlocked: true, submissions: [sub({ status: 'approved' })] }))
    render(<SrsPanel projectId={7} />)
    expect(await screen.findByText('Implementation unlocked')).toBeInTheDocument()
    expect(screen.getByText(/your srs has been approved/i)).toBeInTheDocument()
  })

  it('downloads a submitted version', async () => {
    const s = sub()
    svc.srsService.get.mockResolvedValue(summary({ status: 'submitted', can_submit: false, submissions: [s] }))
    render(<SrsPanel projectId={7} />)
    await userEvent.click(await screen.findByRole('button', { name: /download version 1/i }))
    expect(svc.srsService.download).toHaveBeenCalledWith(s)
  })
})

describe('SRS panel – mentor review', () => {
  beforeEach(() => { mockUser = { id: 4, name: 'Mia', role: 'mentor' } })
  const submitted = () => summary({ stage: 'srs_submitted', status: 'submitted', status_label: 'Submitted', can_submit: false, submissions: [sub()] })

  it('has no submit form but shows the review controls', async () => {
    svc.srsService.get.mockResolvedValue(submitted())
    render(<SrsPanel projectId={7} />)
    expect(await screen.findByRole('button', { name: /^approve$/i })).toBeInTheDocument()
    for (const n of [/start review/i, /request changes/i, /^reject$/i]) expect(screen.getByRole('button', { name: n })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /submit srs/i })).not.toBeInTheDocument()
  })

  it('requires comments to reject or request changes, but not to approve', async () => {
    svc.srsService.get.mockResolvedValue(submitted())
    svc.srsService.review.mockResolvedValue(summary({ status: 'approved', status_label: 'Approved', implementation_unlocked: true, submissions: [sub({ status: 'approved' })] }))
    render(<SrsPanel projectId={7} />)
    await userEvent.click(await screen.findByRole('button', { name: /request changes/i }))
    expect(await screen.findByText(/comments are required when rejecting/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /^reject$/i }))
    expect(svc.srsService.review).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: /^approve$/i }))
    await waitFor(() => expect(svc.srsService.review).toHaveBeenCalledWith(11, 'approve', ''))
    expect(await screen.findByText('Implementation unlocked')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^approve$/i })).not.toBeInTheDocument()   // decided → controls gone
  })

  it('sends comments with a requested modification', async () => {
    svc.srsService.get.mockResolvedValue(submitted())
    svc.srsService.review.mockResolvedValue(summary({ status: 'changes_requested', status_label: 'Changes Requested', submissions: [sub({ status: 'changes_requested' })] }))
    render(<SrsPanel projectId={7} />)
    await userEvent.type(await screen.findByLabelText(/comments/i), 'Add non-functional requirements')
    await userEvent.click(screen.getByRole('button', { name: /request changes/i }))
    await waitFor(() => expect(svc.srsService.review).toHaveBeenCalledWith(11, 'request_changes', 'Add non-functional requirements'))
  })

  it('offers "Start review" only while merely submitted', async () => {
    svc.srsService.get.mockResolvedValue(summary({ stage: 'srs_under_review', status: 'under_review', status_label: 'Under Review', can_submit: false, submissions: [sub({ status: 'under_review' })] }))
    render(<SrsPanel projectId={7} />)
    expect(await screen.findByRole('button', { name: /^approve$/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /start review/i })).not.toBeInTheDocument()
  })

  it('shows the server error when the review is refused', async () => {
    svc.srsService.get.mockResolvedValue(submitted())
    svc.srsService.review.mockRejectedValue({ response: { status: 409, data: { message: 'Only the latest SRS version can be reviewed' } } })
    render(<SrsPanel projectId={7} />)
    await userEvent.click(await screen.findByRole('button', { name: /^approve$/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/latest SRS version/)
  })

  it('is read-only for domain leads', async () => {
    mockUser = { id: 3, name: 'Lea', role: 'domain_lead' }
    svc.srsService.get.mockResolvedValue(submitted())
    render(<SrsPanel projectId={7} />)
    await screen.findByRole('listitem', { name: 'SRS version 1' })
    expect(screen.queryByRole('button', { name: /^approve$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /submit srs/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /download version 1/i })).toBeInTheDocument()
  })
})

describe('GitHub panel', () => {
  it('is locked until the SRS is approved', async () => {
    svc.githubService.get.mockResolvedValue({ repository: null, can_edit: true, implementation_unlocked: false })
    render(<GithubPanel projectId={7} />)
    expect(await screen.findByText(/once your srs is approved/i)).toBeInTheDocument()
    expect(screen.queryByLabelText(/repository url/i)).not.toBeInTheDocument()
  })

  it('validates the URL on the client and saves a valid one', async () => {
    svc.githubService.get.mockResolvedValue({ repository: null, can_edit: true, implementation_unlocked: true })
    svc.githubService.set.mockResolvedValue({ repository: { url: 'https://github.com/o/r', description: 'API' }, can_edit: true, implementation_unlocked: true })
    render(<GithubPanel projectId={7} />)
    const input = await screen.findByLabelText(/repository url/i)
    for (const bad of ['https://gitlab.com/o/r', 'github.com/o/r', 'https://github.com/o', 'https://github.com/o/r/tree/main']) {
      await userEvent.clear(input)
      await userEvent.type(input, bad)
      await userEvent.click(screen.getByRole('button', { name: /save repository/i }))
      expect(await screen.findByText(/valid github repository url/i)).toBeInTheDocument()
    }
    expect(svc.githubService.set).not.toHaveBeenCalled()
    await userEvent.clear(input)
    await userEvent.type(input, 'https://github.com/o/r')
    await userEvent.type(screen.getByLabelText(/project description/i), 'API')
    await userEvent.click(screen.getByRole('button', { name: /save repository/i }))
    await waitFor(() => expect(svc.githubService.set).toHaveBeenCalledWith(7, 'https://github.com/o/r', 'API'))
    expect(await screen.findByText('Repository saved.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /github.com\/o\/r/ })).toHaveAttribute('rel', 'noreferrer noopener')
    expect(screen.getByRole('button', { name: /update repository/i })).toBeInTheDocument()
  })

  it('shows server-side URL errors', async () => {
    svc.githubService.get.mockResolvedValue({ repository: null, can_edit: true, implementation_unlocked: true })
    svc.githubService.set.mockRejectedValue({ response: { status: 422, data: { message: 'Enter a valid GitHub repository URL', errors: { url: 'Not a valid GitHub repository URL' } } } })
    render(<GithubPanel projectId={7} />)
    await userEvent.type(await screen.findByLabelText(/repository url/i), 'https://github.com/o/r')
    await userEvent.click(screen.getByRole('button', { name: /save repository/i }))
    expect(await screen.findByText('Not a valid GitHub repository URL')).toBeInTheDocument()
  })

  it('is read-only for mentors and leads, showing the link', async () => {
    mockUser = { id: 4, name: 'Mia', role: 'mentor' }
    svc.githubService.get.mockResolvedValue({ repository: { url: 'https://github.com/o/r', description: null }, can_edit: false, implementation_unlocked: true })
    render(<GithubPanel projectId={7} />)
    expect(await screen.findByRole('link', { name: /github.com\/o\/r/ })).toBeInTheDocument()
    expect(screen.queryByLabelText(/repository url/i)).not.toBeInTheDocument()
  })

  it('tells reviewers when nothing has been added', async () => {
    svc.githubService.get.mockResolvedValue({ repository: null, can_edit: false, implementation_unlocked: false })
    render(<GithubPanel projectId={7} />)
    expect(await screen.findByText(/no repository has been added yet/i)).toBeInTheDocument()
  })
})

describe('SRS queue page', () => {
  const ITEM = { id: 7, title: 'Smart Attendance', batch: { code: 'B1' }, members: [{ name: 'Asha K' }], srs_version: 2, srs_submitted_at: '2026-03-03T09:00:00', stage: 'srs_submitted' }
  const renderQueue = () => render(<MemoryRouter><SrsQueuePage /></MemoryRouter>)

  it('lists waiting SRS documents with a Review link for mentors', async () => {
    mockUser = { id: 4, name: 'Mia', role: 'mentor' }
    svc.srsService.queue.mockResolvedValue({ items: [ITEM], meta: { page: 1, pages: 1, total: 1 } })
    renderQueue()
    expect(await screen.findByRole('heading', { name: 'SRS Review Queue' })).toBeInTheDocument()
    expect(screen.getByText('v2')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /review/i })).toHaveAttribute('href', '/srs/7')
  })

  it('is a monitoring view for leads and handles an empty queue', async () => {
    mockUser = { id: 3, name: 'Lea', role: 'domain_lead' }
    svc.srsService.queue.mockResolvedValue({ items: [], meta: { page: 1, pages: 1, total: 0 } })
    renderQueue()
    expect(await screen.findByRole('heading', { name: 'SRS Approval Status' })).toBeInTheDocument()
    expect(screen.getByText(/no srs documents are waiting/i)).toBeInTheDocument()
  })
})

describe('navigation', () => {
  it.each([
    ['student', '/student', ['SRS Submission', 'GitHub Repository']],
    ['mentor', '/mentor', ['SRS Review']],
    ['domain_lead', '/lead', ['SRS Status']],
    ['admin', '/admin', ['SRS Queue']],
  ])('%s sees SRS menu entries', async (role, path, labels) => {
    mockUser = { id: 1, name: 'U', role }
    localStorage.setItem('plms_access', 'tok')
    api.get.mockImplementation((url) => Promise.resolve(url === '/auth/me'
      ? { data: { data: { id: 1, name: 'U', email: 'u@x.com', role, must_change_password: false } } }
      : { data: { data: { count: 0 } } }))
    render(<MemoryRouter initialEntries={[path]}><AuthProvider><App /></AuthProvider></MemoryRouter>)
    const nav = await screen.findByRole('navigation', { name: /main navigation/i })
    for (const l of labels) expect(nav).toHaveTextContent(l)
  })
})
