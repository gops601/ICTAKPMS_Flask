import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MentorWorkload from './pages/common/MentorWorkload'
import MyMentorsCard from './components/MyMentorsCard'
import BulkTasksModal from './components/BulkTasksModal'
import AllocatePage from './pages/common/AllocatePage'
import * as svc from './services/adminService'

vi.mock('./context/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, name: 'Lea', role: 'domain_lead' } }) }))
vi.mock('./services/adminService', async () => {
  const actual = await vi.importActual('./services/adminService')
  return {
    ...actual,
    userService: { mentors: vi.fn() },
    mentorService: { transfer: vi.fn(), mine: vi.fn() },
    scrumService: { bulkTemplate: vi.fn(), bulkUpload: vi.fn() },
    batchService: { get: vi.fn() },
    batchMentorService: { list: vi.fn() },
    studentService: { list: vi.fn() },
    psService: { list: vi.fn() },
    projectService: { allocate: vi.fn() },
  }
})

beforeEach(() => vi.clearAllMocks())

describe('replace / remove a mentor', () => {
  const mentors = { items: [
    { id: 1, user_id: 11, name: 'Mia Mentor', email: 'm@x.com', is_active: true, mentor_type: 'internal', batch_count: 1, project_count: 2 },
    { id: 2, user_id: 12, name: 'Ned Mentor', email: 'n@x.com', is_active: true, mentor_type: 'internal', batch_count: 0, project_count: 0 },
  ], meta: { page: 1, pages: 1, total: 2 } }

  it('hands a mentor’s batches and projects to the chosen replacement', async () => {
    svc.userService.mentors.mockResolvedValue(mentors)
    svc.mentorService.transfer.mockResolvedValue({ message: 'Mia Mentor: 1 batch(es) and 2 project(s) moved to Ned Mentor' })
    render(<MemoryRouter><MentorWorkload /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button', { name: 'Replace or remove Mia Mentor' }))
    const dialog = await screen.findByRole('dialog')
    await waitFor(() => expect(within(dialog).getByRole('option', { name: /Ned Mentor/ })).toBeInTheDocument())
    expect(within(dialog).queryByRole('option', { name: /Mia Mentor/ })).not.toBeInTheDocument()   // not offered as their own replacement
    await userEvent.selectOptions(within(dialog).getByLabelText(/hand their batches/i), '2')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Reassign' }))
    await waitFor(() => expect(svc.mentorService.transfer).toHaveBeenCalledWith(1, 2))
    expect(await screen.findByText(/moved to Ned Mentor/)).toBeInTheDocument()
  })

  it('can remove a mentor without a replacement', async () => {
    svc.userService.mentors.mockResolvedValue(mentors)
    svc.mentorService.transfer.mockResolvedValue({ message: 'done' })
    render(<MemoryRouter><MentorWorkload /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button', { name: 'Replace or remove Mia Mentor' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Remove mentor' }))
    await waitFor(() => expect(svc.mentorService.transfer).toHaveBeenCalledWith(1, null))
  })
})

describe('student sees their mentors', () => {
  it('lists the mentors by name only', async () => {
    svc.mentorService.mine.mockResolvedValue([{ id: 1, name: 'Mia Mentor' }, { id: 2, name: 'Ned Mentor' }])
    render(<MyMentorsCard />)
    expect(await screen.findByText('Mia Mentor')).toBeInTheDocument()
    expect(screen.getByText('Ned Mentor')).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it('renders nothing when there are none', async () => {
    svc.mentorService.mine.mockResolvedValue([])
    const { container } = render(<MyMentorsCard />)
    await waitFor(() => expect(svc.mentorService.mine).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })
})

describe('weekly bulk task upload', () => {
  it('downloads the template and reports row errors without adding anything', async () => {
    svc.scrumService.bulkUpload.mockResolvedValue({ created: 0, errors: [{ row: 3, message: "'x@y.com' is not a member of this project" }] })
    const onDone = vi.fn()
    render(<BulkTasksModal projectId={7} onClose={vi.fn()} onDone={onDone} />)
    await userEvent.click(screen.getByRole('button', { name: /excel/i }))
    expect(svc.scrumService.bulkTemplate).toHaveBeenCalledWith(7, 'xlsx')
    expect(screen.getByRole('button', { name: /upload tasks/i })).toBeDisabled()
    const file = new File(['Task Title\nOne'], 'tasks.csv', { type: 'text/csv' })
    await userEvent.upload(screen.getByLabelText(/upload the filled file/i), file)
    await userEvent.click(screen.getByRole('button', { name: /upload tasks/i }))
    expect(await screen.findByText(/Row 3: 'x@y.com' is not a member/)).toBeInTheDocument()
    expect(onDone).not.toHaveBeenCalled()
  })

  it('refreshes the board when tasks were added', async () => {
    const board = { columns: [] }
    svc.scrumService.bulkUpload.mockResolvedValue({ created: 2, errors: [], board })
    const onDone = vi.fn()
    render(<BulkTasksModal projectId={7} onClose={vi.fn()} onDone={onDone} />)
    await userEvent.upload(screen.getByLabelText(/upload the filled file/i), new File(['a'], 'tasks.csv'))
    await userEvent.click(screen.getByRole('button', { name: /upload tasks/i }))
    expect(await screen.findByText(/2 task\(s\) were added/)).toBeInTheDocument()
    expect(onDone).toHaveBeenCalledWith(board)
  })
})

describe('Academic OU project type', () => {
  const setup = (ou) => {
    svc.batchService.get.mockResolvedValue({ id: 5, code: 'B5', domain: { id: 1, name: 'AI' }, ou })
    svc.studentService.list.mockResolvedValue({ items: [{ id: 1, name: 'Stu', registration_no: 'R1', project: null }] })
    svc.psService.list.mockResolvedValue({ items: [{ id: 3, ps_code: 'PS3', title: 'Chatbot', difficulty: 'easy' }] })
    svc.batchMentorService.list.mockResolvedValue([])
    svc.projectService.allocate.mockResolvedValue([])
    render(<MemoryRouter initialEntries={['/lead/batches/5/allocate']}>
      <Routes><Route path="/lead/batches/:id/allocate" element={<AllocatePage />} /><Route path="*" element={<p>done</p>} /></Routes>
    </MemoryRouter>)
  }
  const fill = async () => {
    await userEvent.selectOptions(await screen.findByLabelText(/project \(from the project shelf\)/i), '3')
    await userEvent.click(screen.getByLabelText('Select Stu'))
  }

  it('asks for a type for Academic OU batches and sends it', async () => {
    setup({ id: 1, name: 'Academic OU', code: 'ACADEMIC' })
    await fill()
    await userEvent.click(screen.getByRole('button', { name: /^allocate$/i }))
    expect(await screen.findByText('Choose the project type.')).toBeInTheDocument()
    expect(svc.projectService.allocate).not.toHaveBeenCalled()
    expect(within(screen.getByLabelText(/project type/i)).getAllByRole('option').map((o) => o.textContent))
      .toEqual(['Select…', 'Add-on Course', 'Summer Internship', 'Other'])
    await userEvent.selectOptions(screen.getByLabelText(/project type/i), 'summer_internship')
    await userEvent.click(screen.getByRole('button', { name: /^allocate$/i }))
    await waitFor(() => expect(svc.projectService.allocate.mock.calls[0][0].project_type).toBe('summer_internship'))
  })

  it('has no project type for other OUs', async () => {
    setup({ id: 2, name: 'Retail OU', code: 'RETAIL' })
    await fill()
    expect(screen.queryByLabelText(/project type/i)).not.toBeInTheDocument()
  })
})
