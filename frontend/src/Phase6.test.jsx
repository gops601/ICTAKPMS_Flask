import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ScrumBoard, { applyMove } from './components/ScrumBoard'
import { ScrumOverviewPage } from './pages/common/ScrumPages'
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
    scrumService: { board: vi.fn(), task: vi.fn(), create: vi.fn(), update: vi.fn(), move: vi.fn(), remove: vi.fn(), comment: vi.fn(), overview: vi.fn() },
    notificationService: { unreadCount: vi.fn().mockResolvedValue(0), list: vi.fn(), markRead: vi.fn(), readAll: vi.fn() },
  }
})

const task = (id, title, status, over = {}) => ({
  id, title, status, position: 0, priority: 'medium', description: null, assignee: null, created_by: { id: 1, name: 'Stu' },
  start_date: null, due_date: null, completed_at: null, is_overdue: false, comment_count: 0, version: 1, created_at: '2026-03-02T10:00:00', ...over,
})
const LABELS = { backlog: 'Backlog', todo: 'To Do', in_progress: 'In Progress', in_review: 'In Review', completed: 'Completed' }
const makeBoard = (tasks, perms = {}, over = {}) => ({
  project: { id: 7, title: 'Smart Attendance', stage: 'implementation', mentor_can_edit_board: false },
  permissions: { can_create: true, can_edit: true, can_delete: true, can_move: true, can_comment: true, reason: null, ...perms },
  members: [{ student_id: 1, name: 'Asha K' }, { student_id: 2, name: 'Ben J' }],
  columns: Object.keys(LABELS).map((s) => ({ status: s, label: LABELS[s], tasks: tasks.filter((t) => t.status === s).map((t, i) => ({ ...t, position: i })) })),
  stats: { total: tasks.length, completed: tasks.filter((t) => t.status === 'completed').length, overdue: tasks.filter((t) => t.is_overdue).length, completion_pct: 0, by_status: {} },
  ...over,
})
const col = (name) => within(screen.getByRole('region', { name }))
const renderBoard = () => render(<MemoryRouter><ScrumBoard projectId={7} /></MemoryRouter>)

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  mockUser = { id: 1, name: 'Stu', role: 'student' }
  svc.notificationService.unreadCount.mockResolvedValue(0)
})

describe('applyMove (optimistic ordering)', () => {
  const b = makeBoard([task(1, 'A', 'backlog'), task(2, 'B', 'backlog'), task(3, 'C', 'backlog'), task(4, 'D', 'todo')])
  const ids = (board, s) => board.columns.find((c) => c.status === s).tasks.map((t) => t.id)
  it('reorders within a column', () => expect(ids(applyMove(b, 3, 'backlog', 0), 'backlog')).toEqual([3, 1, 2]))
  it('moves across columns and resequences both', () => {
    const r = applyMove(b, 2, 'todo', 0)
    expect(ids(r, 'backlog')).toEqual([1, 3])
    expect(ids(r, 'todo')).toEqual([2, 4])
    expect(r.columns.find((c) => c.status === 'todo').tasks.map((t) => t.position)).toEqual([0, 1])
    expect(r.columns.find((c) => c.status === 'todo').tasks[0].status).toBe('todo')
  })
  it('appends when no index is given and clamps out-of-range indexes', () => {
    expect(ids(applyMove(b, 1, 'todo', null), 'todo')).toEqual([4, 1])
    expect(ids(applyMove(b, 1, 'todo', 99), 'todo')).toEqual([4, 1])
    expect(ids(applyMove(b, 1, 'todo', -3), 'todo')).toEqual([1, 4])
  })
  it('ignores unknown tasks', () => expect(applyMove(b, 999, 'todo', 0)).toBe(b))
})

describe('board rendering', () => {
  it('shows the five columns with their tasks, priorities, assignees and overdue marks', async () => {
    svc.scrumService.board.mockResolvedValue(makeBoard([
      task(1, 'Design DB', 'backlog', { priority: 'critical', assignee: { student_id: 1, name: 'Asha K' }, due_date: '2026-03-01', is_overdue: true, comment_count: 2 }),
      task(2, 'Write API', 'in_progress'), task(3, 'Release', 'completed')]))
    renderBoard()
    expect(await screen.findByRole('region', { name: 'Backlog' })).toBeInTheDocument()
    for (const l of Object.values(LABELS)) expect(screen.getByRole('region', { name: l })).toBeInTheDocument()
    const backlog = col('Backlog')
    expect(backlog.getByText('Design DB')).toBeInTheDocument()
    expect(backlog.getByText('critical')).toBeInTheDocument()
    expect(backlog.getByText('Asha K')).toBeInTheDocument()
    expect(backlog.getByText(/2026-03-01 · overdue/)).toBeInTheDocument()
    expect(col('To Do').getByText('No tasks')).toBeInTheDocument()
    expect(screen.getByLabelText('Board summary')).toHaveTextContent('3 tasks')
  })

  it('is read-only for leads: no create button, no drag handles or move selects, reason shown', async () => {
    mockUser = { id: 3, name: 'Lea', role: 'domain_lead' }
    svc.scrumService.board.mockResolvedValue(makeBoard([task(1, 'A', 'todo')], { can_create: false, can_edit: false, can_move: false, can_delete: false, can_comment: false, reason: 'You have read-only access to this board.' }))
    renderBoard()
    expect(await screen.findByText(/read-only access/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /new task/i })).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/move a to column/i)).not.toBeInTheDocument()
    expect(screen.getByTestId('task-1')).toHaveAttribute('draggable', 'false')
  })

  it('shows the locked message and no create button before SRS approval', async () => {
    svc.scrumService.board.mockResolvedValue(makeBoard([], { can_create: false, can_edit: false, can_move: false, reason: 'The Scrum board unlocks once your SRS is approved.' }))
    renderBoard()
    expect(await screen.findByText(/unlocks once your srs is approved/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /new task/i })).not.toBeInTheDocument()
  })
})

describe('drag and drop & moving', () => {
  const setup = async () => {
    svc.scrumService.board.mockResolvedValue(makeBoard([task(1, 'A', 'backlog'), task(2, 'B', 'backlog'), task(3, 'C', 'todo')]))
    renderBoard()
    await screen.findByText('A')
  }

  it('drops a card on another column → append', async () => {
    await setup()
    svc.scrumService.move.mockResolvedValue(makeBoard([task(1, 'A', 'in_progress'), task(2, 'B', 'backlog'), task(3, 'C', 'todo')]))
    fireEvent.dragStart(screen.getByTestId('task-1'))
    fireEvent.dragOver(screen.getByTestId('col-in_progress'))
    fireEvent.drop(screen.getByTestId('col-in_progress'))
    await waitFor(() => expect(svc.scrumService.move).toHaveBeenCalledWith(1, 'in_progress', null))
    await waitFor(() => expect(col('In Progress').getByText('A')).toBeInTheDocument())
    expect(col('Backlog').queryByText('A')).not.toBeInTheDocument()
  })

  it('drops a card onto another card → inserted before it', async () => {
    await setup()
    svc.scrumService.move.mockResolvedValue(makeBoard([task(2, 'B', 'backlog'), task(1, 'A', 'backlog'), task(3, 'C', 'todo')]))
    fireEvent.dragStart(screen.getByTestId('task-2'))
    fireEvent.drop(screen.getByTestId('task-1'))
    await waitFor(() => expect(svc.scrumService.move).toHaveBeenCalledWith(2, 'backlog', 0))
  })

  it('dropping a card onto itself does nothing', async () => {
    await setup()
    fireEvent.dragStart(screen.getByTestId('task-1'))
    fireEvent.drop(screen.getByTestId('task-1'))
    expect(svc.scrumService.move).not.toHaveBeenCalled()
  })

  it('updates the UI optimistically then rolls back and shows the error if the server refuses', async () => {
    await setup()
    let reject
    svc.scrumService.move.mockReturnValue(new Promise((_, r) => { reject = r }))
    fireEvent.dragStart(screen.getByTestId('task-1'))
    fireEvent.drop(screen.getByTestId('col-completed'))
    expect(col('Completed').getByText('A')).toBeInTheDocument()                       // optimistic
    reject({ response: { status: 403, data: { message: 'This project is completed; the board is read-only.' } } })
    expect(await screen.findByRole('alert')).toHaveTextContent(/read-only/)
    await waitFor(() => expect(col('Backlog').getByText('A')).toBeInTheDocument())    // rolled back
    expect(col('Completed').queryByText('A')).not.toBeInTheDocument()
  })

  it('supports moving with the keyboard-friendly select', async () => {
    await setup()
    svc.scrumService.move.mockResolvedValue(makeBoard([task(1, 'A', 'backlog'), task(2, 'B', 'in_review'), task(3, 'C', 'todo')]))
    await userEvent.selectOptions(screen.getByLabelText('Move B to column'), 'in_review')
    await waitFor(() => expect(svc.scrumService.move).toHaveBeenCalledWith(2, 'in_review', null))
  })
})

describe('creating and editing tasks', () => {
  it('creates a task with all fields and refreshes the board', async () => {
    svc.scrumService.board.mockResolvedValue(makeBoard([]))
    svc.scrumService.create.mockResolvedValue({})
    renderBoard()
    await userEvent.click(await screen.findByRole('button', { name: /new task/i }))
    const dialog = screen.getByRole('dialog')
    await userEvent.type(within(dialog).getByLabelText(/title/i), 'Build login')
    await userEvent.type(within(dialog).getByLabelText(/description/i), 'JWT based')
    await userEvent.selectOptions(within(dialog).getByLabelText(/priority/i), 'high')
    await userEvent.click(within(dialog).getByRole('checkbox', { name: 'Ben J' }))
    await userEvent.click(within(dialog).getByRole('checkbox', { name: 'Asha K' }))
    await userEvent.selectOptions(within(dialog).getByLabelText(/column/i), 'todo')
    fireEvent.change(within(dialog).getByLabelText(/start date/i), { target: { value: '2026-03-02' } })
    fireEvent.change(within(dialog).getByLabelText(/due date/i), { target: { value: '2026-03-09' } })
    await userEvent.click(within(dialog).getByRole('button', { name: /create task/i }))
    await waitFor(() => expect(svc.scrumService.create).toHaveBeenCalledWith(7, {
      title: 'Build login', description: 'JWT based', priority: 'high', assigned_student_ids: [2, 1],
      start_date: '2026-03-02', due_date: '2026-03-09', status: 'todo' }))
    await waitFor(() => expect(svc.scrumService.board).toHaveBeenCalledTimes(2))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows field errors from the server and keeps the dialog open', async () => {
    svc.scrumService.board.mockResolvedValue(makeBoard([]))
    svc.scrumService.create.mockRejectedValue({ response: { status: 422, data: { message: 'Validation failed', errors: { due_date: 'Due date cannot be before the start date' } } } })
    renderBoard()
    await userEvent.click(await screen.findByRole('button', { name: /new task/i }))
    await userEvent.type(screen.getByLabelText(/title/i), 'X')
    await userEvent.click(screen.getByRole('button', { name: /create task/i }))
    expect((await screen.findAllByText(/due date cannot be before/i)).length).toBeGreaterThan(0)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  const open = async (t, perms) => {
    svc.scrumService.board.mockResolvedValue(makeBoard([t], perms))
    svc.scrumService.task.mockResolvedValue({ ...t, comments: [], history: [{ id: 1, action: 'created', field: 'status', old: null, new: 'backlog', user: 'Stu', at: '2026-03-02T10:00:00' }] })
    renderBoard()
    await userEvent.click(await screen.findByRole('button', { name: `Open task ${t.title}` }))
    return screen.findByRole('dialog')
  }

  it('edits a task sending the version for conflict detection', async () => {
    const dialog = await open(task(5, 'Old title', 'backlog', { version: 3 }))
    svc.scrumService.update.mockResolvedValue({ ...task(5, 'New title', 'backlog', { version: 4 }), comments: [], history: [] })
    const title = within(dialog).getByLabelText(/title/i)
    await userEvent.clear(title)
    await userEvent.type(title, 'New title')
    await userEvent.click(within(dialog).getByRole('button', { name: /save changes/i }))
    await waitFor(() => expect(svc.scrumService.update).toHaveBeenCalled())
    expect(svc.scrumService.update.mock.calls[0]).toEqual([5, expect.objectContaining({ title: 'New title', version: 3 })])
  })

  it('shows the conflict message when someone else changed the task', async () => {
    const dialog = await open(task(5, 'T', 'backlog'))
    svc.scrumService.update.mockRejectedValue({ response: { status: 409, data: { message: 'This task was changed by someone else. Reload and try again.' } } })
    await userEvent.click(within(dialog).getByRole('button', { name: /save changes/i }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(/changed by someone else/)
  })

  it('only offers delete for tasks that have not started, after confirmation', async () => {
    const dialog = await open(task(5, 'Todo task', 'todo'))
    svc.scrumService.remove.mockResolvedValue({})
    await userEvent.click(within(dialog).getByRole('button', { name: /delete task/i }))
    expect(svc.scrumService.remove).not.toHaveBeenCalled()
    const confirm = screen.getAllByRole('dialog').at(-1)
    await userEvent.click(within(confirm).getByRole('button', { name: /delete task/i }))
    await waitFor(() => expect(svc.scrumService.remove).toHaveBeenCalledWith(5))
  })

  it('hides delete for in-progress tasks', async () => {
    const dialog = await open(task(6, 'Started', 'in_progress'))
    expect(within(dialog).queryByRole('button', { name: /delete task/i })).not.toBeInTheDocument()
  })

  it('shows the history tab with who did what', async () => {
    const dialog = await open(task(7, 'H', 'backlog'))
    await userEvent.click(within(dialog).getByRole('tab', { name: 'History' }))
    expect(within(dialog).getByText('created')).toBeInTheDocument()
    expect(within(dialog).getByText(/Stu ·/)).toBeInTheDocument()
  })

  it('posts comments and shows them', async () => {
    const dialog = await open(task(8, 'C', 'backlog'))
    svc.scrumService.comment.mockResolvedValue({ ...task(8, 'C', 'backlog', { comment_count: 1 }), history: [],
      comments: [{ id: 1, body: 'Looks good', user: 'Stu', created_at: '2026-03-02T11:00:00' }] })
    await userEvent.click(within(dialog).getByRole('tab', { name: /comments/i }))
    await userEvent.type(within(dialog).getByLabelText(/add a comment/i), 'Looks good')
    await userEvent.click(within(dialog).getByRole('button', { name: /post comment/i }))
    expect(await within(dialog).findByText('Looks good')).toBeInTheDocument()
    expect(svc.scrumService.comment).toHaveBeenCalledWith(8, 'Looks good')
  })

  it('lets a mentor comment but not edit; leads see comments read-only', async () => {
    mockUser = { id: 4, name: 'Mia', role: 'mentor' }
    const perms = { can_create: false, can_edit: false, can_delete: false, can_move: false, can_comment: true, reason: 'Mentors can view the board and comment.' }
    const dialog = await open(task(9, 'M', 'backlog'), perms)
    expect(within(dialog).getByLabelText(/title/i)).toBeDisabled()
    expect(within(dialog).queryByRole('button', { name: /save changes/i })).not.toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('tab', { name: /comments/i }))
    expect(within(dialog).getByLabelText(/add a comment/i)).toBeInTheDocument()
  })

  it('renders comment text as plain text (no HTML execution)', async () => {
    svc.scrumService.board.mockResolvedValue(makeBoard([task(10, 'X', 'backlog')]))
    svc.scrumService.task.mockResolvedValue({ ...task(10, 'X', 'backlog', { comment_count: 1 }), history: [],
      comments: [{ id: 1, body: '<img src=x onerror=alert(1)>', user: 'Evil', created_at: '2026-03-02T11:00:00' }] })
    renderBoard()
    await userEvent.click(await screen.findByRole('button', { name: 'Open task X' }))
    await userEvent.click(await screen.findByRole('tab', { name: /comments/i }))
    expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeInTheDocument()
    expect(document.querySelector('img[src="x"]')).toBeNull()
  })
})

describe('scrum monitoring page', () => {
  const ITEM = { project_id: 7, title: 'Smart Attendance', stage: 'implementation', stage_label: 'Implementation', batch: { id: 1, code: 'B1' }, members: ['Asha K'],
    stats: { total: 5, completed: 2, completion_pct: 40, overdue: 1, by_status: { in_progress: 2, in_review: 1 } } }
  it('lists boards with stats and links to each board; toggles the overdue filter', async () => {
    mockUser = { id: 4, name: 'Mia', role: 'mentor' }
    svc.scrumService.overview.mockResolvedValue({ items: [ITEM], meta: { page: 1, pages: 1, total: 1 } })
    render(<MemoryRouter><ScrumOverviewPage /></MemoryRouter>)
    expect(await screen.findByText('Smart Attendance')).toBeInTheDocument()
    expect(screen.getByText('2 (40%)')).toBeInTheDocument()
    expect(screen.getByText('2 / 1')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /open board/i })).toHaveAttribute('href', '/scrum/7')
    await userEvent.click(screen.getByLabelText(/only projects with overdue/i))
    await waitFor(() => expect(svc.scrumService.overview).toHaveBeenLastCalledWith({ page: 1, overdue: 1 }))
  })
})

describe('navigation', () => {
  it.each([['student', '/student', 'Scrum Board'], ['mentor', '/mentor', 'Scrum Monitoring'], ['domain_lead', '/lead', 'Scrum Monitoring'], ['admin', '/admin', 'Scrum Monitoring']])(
    '%s sees the Scrum menu entry', async (role, path, label) => {
      mockUser = { id: 1, name: 'U', role }
      localStorage.setItem('plms_access', 'tok')
      api.get.mockImplementation((url) => Promise.resolve(url === '/auth/me'
        ? { data: { data: { id: 1, name: 'U', email: 'u@x.com', role, must_change_password: false } } } : { data: { data: { count: 0 } } }))
      render(<MemoryRouter initialEntries={[path]}><AuthProvider><App /></AuthProvider></MemoryRouter>)
      expect(await screen.findByRole('navigation', { name: /main navigation/i })).toHaveTextContent(label)
    })
})
