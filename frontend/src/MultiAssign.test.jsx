import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProjectList from './pages/common/ProjectList'
import DateChangeButton from './components/DateChangeButton'
import * as svc from './services/adminService'

let mockUser = { id: 3, name: 'Lea', role: 'domain_lead' }
vi.mock('./context/AuthContext', () => ({ useAuth: () => ({ user: mockUser }) }))
vi.mock('./components/BatchFilter', () => ({ default: () => null }))
vi.mock('./services/adminService', async () => {
  const actual = await vi.importActual('./services/adminService')
  return {
    ...actual,
    projectService: { list: vi.fn(), setMentors: vi.fn() },
    batchMentorService: { list: vi.fn() },
    userService: { mentors: vi.fn() },
    reviewDateService: { create: vi.fn() },
  }
})

const P = { id: 7, code: 'ICT_PRJ_1', title: 'Smart Attendance', stage: 'implementation', stage_label: 'Implementation', progress: 10, is_delayed: false,
  batch: { id: 1, code: 'B1' }, problem_statement: { ps_code: 'PS1' }, members: [{ name: 'Asha' }], mentors: [{ id: 9, name: 'Mia Mentor' }], mentor_override: false }

beforeEach(() => { vi.clearAllMocks(); mockUser = { id: 3, name: 'Lea', role: 'domain_lead' }; svc.projectService.list.mockResolvedValue({ items: [P], meta: { page: 1, pages: 1, total: 1 } }) })

describe('assign mentors from the project list', () => {
  it('shows an Assign mentor button next to Open and saves several mentors', async () => {
    svc.batchMentorService.list.mockResolvedValue([{ id: 9, name: 'Mia Mentor' }, { id: 10, name: 'Max Mentor' }])
    svc.projectService.setMentors.mockResolvedValue({})
    render(<MemoryRouter><ProjectList /></MemoryRouter>)
    expect(await screen.findByRole('link', { name: /open/i })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /assign mentors to smart attendance/i }))
    await userEvent.click(await screen.findByRole('checkbox', { name: 'Mia Mentor' }))
    await userEvent.click(screen.getByRole('checkbox', { name: 'Max Mentor' }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^save$/i }))
    await waitFor(() => expect(svc.projectService.setMentors).toHaveBeenCalledWith(7, [9, 10], ''))
  })

  it('is not offered to mentors', async () => {
    mockUser = { id: 4, name: 'Mia', role: 'mentor' }
    render(<MemoryRouter><ProjectList /></MemoryRouter>)
    await screen.findByRole('link', { name: /open/i })
    expect(screen.queryByRole('button', { name: /assign mentors/i })).not.toBeInTheDocument()
  })
})

describe('mentor review date change button', () => {
  const review = (can) => ({ id: 5, week_no: 2, review_date: '2026-12-01', permissions: { can_request_date_change: can } })

  it('is hidden unless the API allows it', () => {
    const { container } = render(<DateChangeButton review={review(false)} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('sends the new date and a reason', async () => {
    svc.reviewDateService.create.mockResolvedValue({})
    const done = vi.fn()
    render(<DateChangeButton review={review(true)} onDone={done} />)
    await userEvent.click(screen.getByRole('button', { name: /change date/i }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /send for approval/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/choose the new date/i)
    const day = new Date(Date.now() + 5 * 864e5).toISOString().slice(0, 10)
    await userEvent.type(screen.getByLabelText(/new review date/i), day)
    await userEvent.type(screen.getByLabelText(/reason/i), 'Students on leave')
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /send for approval/i }))
    await waitFor(() => expect(svc.reviewDateService.create).toHaveBeenCalledWith(5, day, 'Students on leave'))
    expect(done).toHaveBeenCalled()
  })
})
