import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import NotificationBell from './components/NotificationBell'
import ProjectView from './components/ProjectView'
import AllocatePage from './pages/common/AllocatePage'
import BatchDetail from './pages/common/BatchDetail'
import App from './App'
import { AuthProvider } from './context/AuthContext'
import api from './services/api'
import * as svc from './services/adminService'

let mockUser = { id: 1, name: 'Stu', role: 'student' }
vi.mock('./hooks/useBasePath', () => ({ default: () => '/lead' }))
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
    feedbackService: { list: vi.fn().mockResolvedValue([]), send: vi.fn() },
    projectService: { list: vi.fn(), get: vi.fn(), timeline: vi.fn(), transition: vi.fn(), close: vi.fn(), reopen: vi.fn(), setMentor: vi.fn(), setBoardPermission: vi.fn(), reassignProblem: vi.fn(), allocate: vi.fn() },
    batchService: { get: vi.fn(), list: vi.fn() },
    batchMentorService: { list: vi.fn(), assign: vi.fn(), remove: vi.fn(), reassign: vi.fn() },
    studentService: { list: vi.fn() },
    psService: { list: vi.fn() },
    userService: { mentors: vi.fn() },
    notificationService: { list: vi.fn(), unreadCount: vi.fn(), markRead: vi.fn(), readAll: vi.fn() },
  }
})

const PROJECT = {
  id: 7, title: 'Smart Attendance', stage: 'allocated', stage_label: 'Project Allocated', progress: 12.5,
  is_delayed: false, delay_reasons: [], mentor_can_edit_board: false, mentor_override: false,
  batch: { id: 2, code: 'B1', name: 'Batch 1', domain: { id: 5, name: 'AI & ML' } },
  problem_statement: { id: 3, ps_code: 'PS-1', title: 'Smart Attendance', difficulty: 'hard' },
  members: [{ student_id: 1, name: 'Asha K', registration_no: 'R1', is_lead: false }],
  mentors: [{ id: 9, name: 'Mia Mentor' }], start_date: '2026-03-02', target_end_date: '2026-03-30',
  reviews: [1, 2, 3, 4].map((w) => ({ week_no: w, due_date: `2026-03-${String(w * 7 + 2).padStart(2, '0')}`, status: 'pending' })),
  available_actions: [{ to: 'srs_preparation', label: 'SRS Preparation', enabled: true, reason: null }],
}
const TIMELINE = [{ kind: 'transition', at: '2026-03-02T10:00:00', actor: 'Lead', from: null, to: 'allocated', reason: null, is_reopen: false }]

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  mockUser = { id: 1, name: 'Stu', role: 'student' }
  svc.projectService.get.mockResolvedValue(PROJECT)
  svc.projectService.timeline.mockResolvedValue(TIMELINE)
})

describe('notification bell', () => {
  const ITEMS = [
    { id: 1, title: 'Project allocated', message: 'You have a project', link: '/student/project', is_read: false, created_at: '2026-03-02T10:00:00' },
    { id: 2, title: 'Mentor assigned', message: null, link: null, is_read: true, created_at: '2026-03-01T10:00:00' },
  ]
  const renderBell = () =>
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes><Route path="/" element={<NotificationBell />} /><Route path="/student/project" element={<div>Project page</div>} /></Routes>
      </MemoryRouter>,
    )

  it('shows the unread count and hides the badge at zero', async () => {
    svc.notificationService.unreadCount.mockResolvedValue(3)
    renderBell()
    expect(await screen.findByTestId('unread-badge')).toHaveTextContent('3')
  })

  it('shows no badge when nothing is unread', async () => {
    svc.notificationService.unreadCount.mockResolvedValue(0)
    renderBell()
    await waitFor(() => expect(svc.notificationService.unreadCount).toHaveBeenCalled())
    expect(screen.queryByTestId('unread-badge')).not.toBeInTheDocument()
  })

  it('opens the list, marks an item read and follows its link', async () => {
    svc.notificationService.unreadCount.mockResolvedValue(1)
    svc.notificationService.list.mockResolvedValue({ items: ITEMS, meta: {} })
    svc.notificationService.markRead.mockResolvedValue({})
    renderBell()
    await userEvent.click(await screen.findByRole('button', { name: /notifications, 1 unread/i }))
    await userEvent.click(await screen.findByRole('menuitem', { name: /project allocated/i }))
    expect(svc.notificationService.markRead).toHaveBeenCalledWith(1)
    expect(await screen.findByText('Project page')).toBeInTheDocument()
  })

  it('marks everything read', async () => {
    svc.notificationService.unreadCount.mockResolvedValue(2)
    svc.notificationService.list.mockResolvedValue({ items: ITEMS, meta: {} })
    svc.notificationService.readAll.mockResolvedValue({})
    renderBell()
    await userEvent.click(await screen.findByRole('button', { name: /notifications/i }))
    await userEvent.click(await screen.findByRole('button', { name: /mark all read/i }))
    expect(svc.notificationService.readAll).toHaveBeenCalled()
    await waitFor(() => expect(screen.queryByTestId('unread-badge')).not.toBeInTheDocument())
  })
})

describe('project view', () => {
  const renderView = () => render(<MemoryRouter><ProjectView id={7} /></MemoryRouter>)

  it('lets the student start SRS preparation and reloads', async () => {
    svc.projectService.transition.mockResolvedValue({})
    renderView()
    await userEvent.click(await screen.findByRole('button', { name: /start srs preparation/i }))
    expect(svc.projectService.transition).toHaveBeenCalledWith(7, 'srs_preparation')
    await waitFor(() => expect(svc.projectService.get).toHaveBeenCalledTimes(2))
  })

  it('shows lifecycle info: stage, mentor, review schedule, timeline; no management controls for students', async () => {
    renderView()
    expect(await screen.findByRole('heading', { name: 'Smart Attendance' })).toBeInTheDocument()
    expect(screen.getByText('Project Allocated', { selector: 'span' })).toBeInTheDocument()
    expect(screen.getByText('Mia Mentor')).toBeInTheDocument()
    expect(screen.getByText('Week 4')).toBeInTheDocument()
    expect(screen.getByText(/Project allocated \(Project Allocated\)/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /assign mentor/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /reopen/i })).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/allow the mentor/i)).not.toBeInTheDocument()
  })

  it('shows a blocked next step with the reason instead of a usable button', async () => {
    svc.projectService.get.mockResolvedValue({ ...PROJECT, stage: 'implementation', available_actions: [
      { to: 'final_evaluation', label: 'Final Evaluation', enabled: false, reason: 'All four weekly reviews must be submitted before the final evaluation' }] })
    mockUser = { id: 4, name: 'Men', role: 'mentor' }
    renderView()
    expect(await screen.findByText(/all four weekly reviews must be submitted/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /move to final evaluation/i })).toBeDisabled()
  })

  it('shows delay reasons', async () => {
    svc.projectService.get.mockResolvedValue({ ...PROJECT, is_delayed: true, delay_reasons: ['2 weekly review(s) overdue'] })
    renderView()
    expect(await screen.findByText(/2 weekly review\(s\) overdue/)).toBeInTheDocument()
    expect(screen.getAllByText('Delayed').length).toBeGreaterThan(0)
  })

  it('requires a reason before an admin reopens, then calls the API', async () => {
    mockUser = { id: 2, name: 'Ad', role: 'admin' }
    svc.projectService.get.mockResolvedValue({ ...PROJECT, stage: 'completed', stage_label: 'Completed', available_actions: [] })
    svc.projectService.reopen.mockResolvedValue({})
    renderView()
    await userEvent.click(await screen.findByRole('button', { name: /^reopen$/i }))
    const dialog = screen.getByRole('dialog')
    await userEvent.selectOptions(within(dialog).getByLabelText(/reopen to/i), 'final_evaluation')
    await userEvent.type(within(dialog).getByLabelText(/reason/i), 'Marks need correction')
    await userEvent.click(within(dialog).getByRole('button', { name: /reopen project/i }))
    expect(svc.projectService.reopen).toHaveBeenCalledWith(7, 'final_evaluation', 'Marks need correction')
  })

  it('shows the server error inside the reopen dialog', async () => {
    mockUser = { id: 2, name: 'Ad', role: 'admin' }
    svc.projectService.get.mockResolvedValue({ ...PROJECT, stage: 'implementation', stage_label: 'Implementation', available_actions: [] })
    svc.projectService.reopen.mockRejectedValue({ response: { status: 422, data: { message: 'A reason (at least 5 characters) is required to reopen a project' } } })
    renderView()
    await userEvent.click(await screen.findByRole('button', { name: /^reopen$/i }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /reopen project/i }))
    expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveTextContent(/at least 5 characters/)
  })

  it('lets a lead assign a project-specific mentor from the batch mentors only', async () => {
    mockUser = { id: 3, name: 'Lea', role: 'domain_lead' }
    svc.batchMentorService.list.mockResolvedValue([{ id: 9, name: 'Mia Mentor' }, { id: 10, name: 'Max Mentor' }])
    svc.projectService.setMentor.mockResolvedValue({})
    renderView()
    await userEvent.click(await screen.findByRole('button', { name: /assign mentor/i }))
    await userEvent.selectOptions(await screen.findByLabelText(/mentor for this project/i), '10')
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^save$/i }))
    expect(svc.projectService.setMentor).toHaveBeenCalledWith(7, 10)
  })

  it('no longer has a mentor board-editing toggle (mentors always change the board)', async () => {
    mockUser = { id: 3, name: 'Lea', role: 'domain_lead' }
    renderView()
    await screen.findByText(/mentor feedback/i)
    expect(screen.queryByLabelText(/allow the mentor/i)).not.toBeInTheDocument()
  })

  it('lets a lead close a completed project, and shows closed projects as closed', async () => {
    mockUser = { id: 3, name: 'Lea', role: 'domain_lead' }
    svc.projectService.get.mockResolvedValue({ ...PROJECT, stage: 'completed', stage_label: 'Completed', is_closed: false, available_actions: [] })
    svc.projectService.close.mockResolvedValue({})
    renderView()
    await userEvent.click(await screen.findByRole('button', { name: /close project/i }))
    const buttons = await screen.findAllByRole('button', { name: /close project/i })
    await userEvent.click(buttons[buttons.length - 1]) // the dialog's confirm button
    await waitFor(() => expect(svc.projectService.close).toHaveBeenCalledWith(7))
  })

  it('lets a mentor send feedback and hides the composer from students', async () => {
    mockUser = { id: 4, name: 'Mia', role: 'mentor' }
    svc.feedbackService.send.mockResolvedValue({})
    renderView()
    await userEvent.type(await screen.findByLabelText(/^feedback$/i), 'Great work')
    await userEvent.click(screen.getByRole('button', { name: /send feedback/i }))
    await waitFor(() => expect(svc.feedbackService.send).toHaveBeenCalledWith(7, 'Great work', null))
  })
})

describe('allocation page', () => {
  const STUDENTS = [
    { id: 1, name: 'Asha K', registration_no: 'R1', project: null },
    { id: 2, name: 'Ben J', registration_no: 'R2', project: null },
    { id: 3, name: 'Cara L', registration_no: 'R3', project: { id: 5, title: 'Existing project', stage: 'allocated' } },
  ]
  beforeEach(() => {
    svc.batchService.get.mockResolvedValue({ id: 2, code: 'B1', domain: { id: 5, name: 'AI & ML' } })
    svc.studentService.list.mockResolvedValue({ items: STUDENTS, meta: {} })
    svc.psService.list.mockResolvedValue({ items: [{ id: 3, ps_code: 'PS-1', title: 'Attendance', difficulty: 'easy' }], meta: {} })
    svc.batchMentorService.list.mockResolvedValue([{ id: 9, name: 'Mia Mentor' }])
  })
  const renderPage = () =>
    render(
      <MemoryRouter initialEntries={['/lead/batches/2/allocate']}>
        <Routes>
          <Route path="/lead/batches/:id/allocate" element={<AllocatePage />} />
          <Route path="/lead/batches/:id" element={<div>Batch page</div>} />
        </Routes>
      </MemoryRouter>,
    )

  it('disables already-allocated students and validates before submitting', async () => {
    renderPage()
    expect(await screen.findByLabelText('Select Cara L')).toBeDisabled()
    expect(screen.getByText(/already allocated: existing project/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /^allocate$/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/choose a project/i)
    await userEvent.selectOptions(screen.getByLabelText(/from the project shelf/i), '3')
    await userEvent.click(screen.getByRole('button', { name: /^allocate$/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/select at least one student/i)
    expect(svc.projectService.allocate).not.toHaveBeenCalled()
  })

  it('sends a team allocation with selected students, mentor and start date', async () => {
    svc.projectService.allocate.mockResolvedValue([])
    renderPage()
    await userEvent.selectOptions(await screen.findByLabelText(/from the project shelf/i), '3')
    await userEvent.click(screen.getByLabelText('Select Asha K'))
    await userEvent.click(screen.getByLabelText('Select Ben J'))
    await userEvent.click(screen.getByLabelText(/one team project/i))
    await userEvent.selectOptions(screen.getByLabelText(/mentor \(optional/i), '9')
    await userEvent.click(screen.getByRole('button', { name: /^allocate$/i }))
    await waitFor(() => expect(svc.projectService.allocate).toHaveBeenCalled())
    expect(svc.projectService.allocate.mock.calls[0][0]).toEqual({
      batch_id: 2, mentor_id: 9, start_date: null,
      items: [{ problem_statement_id: 3, student_ids: [1, 2], team: true }],
    })
    expect(await screen.findByText('Batch page')).toBeInTheDocument()
  })

  it('selects all available students at once (skipping allocated ones)', async () => {
    svc.projectService.allocate.mockResolvedValue([])
    renderPage()
    await userEvent.selectOptions(await screen.findByLabelText(/from the project shelf/i), '3')
    await userEvent.click(screen.getByLabelText(/select all available/i))
    await userEvent.click(screen.getByRole('button', { name: /^allocate$/i }))
    await waitFor(() => expect(svc.projectService.allocate).toHaveBeenCalled())
    expect(svc.projectService.allocate.mock.calls[0][0].items[0]).toMatchObject({ student_ids: [1, 2], team: false })
  })

  it('shows the server error when allocation is rejected', async () => {
    svc.projectService.allocate.mockRejectedValue({ response: { status: 422, data: { message: 'Allocation not possible: Asha K already has a project' } } })
    renderPage()
    await userEvent.selectOptions(await screen.findByLabelText(/from the project shelf/i), '3')
    await userEvent.click(screen.getByLabelText('Select Asha K'))
    await userEvent.click(screen.getByRole('button', { name: /^allocate$/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/already has a project/)
  })
})

describe('batch detail mentors tab', () => {
  const BATCH = { id: 2, code: 'B1', name: 'Batch 1', status: 'active', student_count: 3, details: {}, ou: { name: 'Academic OU' }, domain: { id: 5, name: 'AI & ML' } }
  beforeEach(() => {
    svc.batchService.get.mockResolvedValue(BATCH)
    svc.studentService.list.mockResolvedValue({ items: [], meta: {} })
    svc.batchMentorService.list.mockResolvedValue([{ id: 9, name: 'Mia Mentor', email: 'mia@x.com', designation: 'Senior' }])
    svc.userService.mentors.mockResolvedValue({ items: [
      { id: 9, name: 'Mia Mentor', is_active: true, project_count: 2 }, { id: 10, name: 'Max Mentor', is_active: true, project_count: 0 }], meta: {} })
  })
  const renderDetail = () =>
    render(<MemoryRouter initialEntries={['/lead/batches/2']}><Routes><Route path="/lead/batches/:id" element={<BatchDetail />} /></Routes></MemoryRouter>)

  it('lets a lead assign only not-yet-assigned mentors, showing workload', async () => {
    mockUser = { id: 3, name: 'Lea', role: 'domain_lead' }
    svc.batchMentorService.assign.mockResolvedValue([])
    renderDetail()
    await userEvent.click(await screen.findByRole('tab', { name: 'Mentors' }))
    await userEvent.click(await screen.findByRole('button', { name: /assign mentor/i }))
    const select = await screen.findByLabelText(/^mentor$/i)
    const options = within(select).getAllByRole('option').map((o) => o.textContent)
    expect(options).toEqual(['Select a mentor…', 'Max Mentor (0 projects)'])
    await userEvent.selectOptions(select, '10')
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^assign$/i }))
    expect(svc.batchMentorService.assign).toHaveBeenCalledWith(2, 10)
  })

  it('confirms before removing a mentor and supports reassignment', async () => {
    mockUser = { id: 3, name: 'Lea', role: 'domain_lead' }
    svc.batchMentorService.remove.mockResolvedValue([])
    svc.batchMentorService.reassign.mockResolvedValue([])
    renderDetail()
    await userEvent.click(await screen.findByRole('tab', { name: 'Mentors' }))
    await userEvent.click(await screen.findByRole('button', { name: /remove mia mentor/i }))
    expect(svc.batchMentorService.remove).not.toHaveBeenCalled()
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^remove$/i }))
    await waitFor(() => expect(svc.batchMentorService.remove).toHaveBeenCalledWith(2, 9))

    await userEvent.click(await screen.findByRole('button', { name: /reassign/i }))
    await userEvent.selectOptions(await screen.findByLabelText(/replace with/i), '10')
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^reassign$/i }))
    expect(svc.batchMentorService.reassign).toHaveBeenCalledWith(2, 9, 10)
  })

  it('lets mentors allocate but not assign/reassign/remove mentors', async () => {
    mockUser = { id: 4, name: 'Mia', role: 'mentor' }
    renderDetail()
    await userEvent.click(await screen.findByRole('tab', { name: 'Mentors' }))
    expect(await screen.findByText('Mia Mentor')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /assign mentor/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /reassign/i })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /allocate projects/i })).toBeInTheDocument()
  })

  it('shows the allocate button to leads of an active batch', async () => {
    mockUser = { id: 3, name: 'Lea', role: 'domain_lead' }
    renderDetail()
    expect(await screen.findByRole('link', { name: /allocate projects/i })).toHaveAttribute('href', '/lead/batches/2/allocate')
  })
})

describe('role navigation', () => {
  const asRole = async (role, path) => {
    localStorage.setItem('plms_access', 'tok')
    api.get.mockReset()
    api.get.mockImplementation((url) => Promise.resolve(url === '/auth/me'
      ? { data: { data: { id: 1, name: 'U', email: 'u@x.com', role, must_change_password: false } } }
      : { data: { data: { count: 0 } } }))
    render(<MemoryRouter initialEntries={[path]}><AuthProvider><App /></AuthProvider></MemoryRouter>)
    return screen.findByRole('navigation', { name: /main navigation/i })
  }
  it.each([
    ['domain_lead', '/lead', ['My Batches', 'Mentors', 'Projects', 'Project Shelf', 'Notifications']],
    ['mentor', '/mentor', ['My Batches', 'My Projects', 'Notifications']],
    ['student', '/student', ['My Project', 'Notifications']],
    ['admin', '/admin', ['Project Shelf', 'Projects', 'Domain Leads', 'Mentors', 'Notifications']],
  ])('%s sees their modules', async (role, path, labels) => {
    mockUser = { id: 1, name: 'U', role }
    const nav = await asRole(role, path)
    for (const l of labels) expect(nav).toHaveTextContent(l)
  })

  it('students cannot reach lead pages', async () => {
    await asRole('student', '/lead/batches')
    expect(await screen.findByText(/welcome, stu/i)).toBeInTheDocument()
  })
})
