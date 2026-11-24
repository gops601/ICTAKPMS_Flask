import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MyProposal from './pages/student/MyProposal'
import ShelfReviewButtons from './components/ShelfReviewButtons'
import ProjectTeamModal from './components/ProjectTeamModal'
import * as svc from './services/adminService'

vi.mock('./services/adminService', async () => {
  const actual = await vi.importActual('./services/adminService')
  return {
    ...actual,
    proposalService: { mine: vi.fn(), classmates: vi.fn(), submit: vi.fn(), reviewFromShelf: vi.fn(), projectTemplate: vi.fn(), dataTemplate: vi.fn(), download: vi.fn() },
    studentService: { list: vi.fn() },
    projectService: { setMembers: vi.fn() },
  }
})

beforeEach(() => vi.clearAllMocks())

const INFO = { proposals: [], can_upload: true, domain: { id: 1, name: 'AI' }, subdomains: [], blocked_reason: null, has_project: false }

describe('student chooses individual or group', () => {
  const setup = async () => {
    svc.proposalService.mine.mockResolvedValue(INFO)
    svc.proposalService.classmates.mockResolvedValue({ me: 1, max_group_size: 6, students: [
      { id: 2, name: 'Bina', registration_no: 'R2' }, { id: 3, name: 'Chitra', registration_no: 'R3' }] })
    svc.proposalService.submit.mockResolvedValue({})
    render(<MemoryRouter><MyProposal /></MemoryRouter>)
    await screen.findByRole('radio', { name: /individual project/i })
  }
  const fillBasics = async () => {
    await userEvent.type(screen.getByLabelText(/^title/i), 'Smart Campus')
    await userEvent.upload(screen.getByLabelText(/detailed project proposal/i), new File(['x'], 'detail.pdf', { type: 'application/pdf' }))
  }

  it('is individual by default and sends no group', async () => {
    await setup()
    expect(screen.getByRole('radio', { name: /individual project/i })).toBeChecked()
    expect(screen.queryByRole('list', { name: 'Students' })).not.toBeInTheDocument()
    await fillBasics()
    await userEvent.click(screen.getByRole('button', { name: /submit for approval/i }))
    await waitFor(() => expect(svc.proposalService.submit).toHaveBeenCalled())
    const args = svc.proposalService.submit.mock.calls[0]
    expect(args[6]).toBe('individual')
  })

  it('shows the batch mates, takes roles in one go and submits the group', async () => {
    await setup()
    await userEvent.click(screen.getByRole('radio', { name: /group project/i }))
    const list = await screen.findByRole('list', { name: 'Students' })
    expect(within(list).getAllByRole('checkbox')).toHaveLength(2)
    await userEvent.type(screen.getByLabelText(/your role in the group/i), 'Lead dev')
    await userEvent.click(screen.getByLabelText('Select Bina'))
    await userEvent.type(screen.getByLabelText('Role of Bina'), 'Tester')
    await userEvent.click(screen.getByLabelText('Select Chitra'))
    await fillBasics()
    await userEvent.click(screen.getByRole('button', { name: /submit for approval/i }))
    await waitFor(() => expect(svc.proposalService.submit).toHaveBeenCalled())
    const args = svc.proposalService.submit.mock.calls[0]
    expect(args[6]).toBe('group')
    expect(args[7]).toEqual([{ student_id: 1, role: 'Lead dev' }, { student_id: 2, role: 'Tester' }, { student_id: 3, role: '' }])
  })

  it('will not submit a group with nobody selected', async () => {
    await setup()
    await userEvent.click(screen.getByRole('radio', { name: /group project/i }))
    await screen.findByRole('list', { name: 'Students' })
    await fillBasics()
    await userEvent.click(screen.getByRole('button', { name: /submit for approval/i }))
    expect(await screen.findByText('Select the students who are in your group.')).toBeInTheDocument()
    expect(svc.proposalService.submit).not.toHaveBeenCalled()
  })
})

describe('approve / reject from the Project Shelf', () => {
  const ps = (over = {}) => ({ id: 9, ps_code: 'ICT_PS_AB12CD', title: 'Leaf scanner', proposal: { id: 4, status: 'pending', is_group: true, members: [{ student_id: 1 }, { student_id: 2 }] }, ...over })

  it('lets a mentor or lead approve a pending student project, noting the whole group starts', async () => {
    svc.proposalService.reviewFromShelf.mockResolvedValue({})
    const onDone = vi.fn()
    render(<ShelfReviewButtons ps={ps()} onDone={onDone} />)
    await userEvent.click(screen.getByRole('button', { name: 'Approve ICT_PS_AB12CD' }))
    expect(screen.getByText(/whole group \(2 students\)/)).toBeInTheDocument()
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(svc.proposalService.reviewFromShelf).toHaveBeenCalledWith(9, 'approve', null))
    expect(onDone).toHaveBeenCalled()
  })

  it('needs remarks to reject', async () => {
    svc.proposalService.reviewFromShelf.mockResolvedValue({})
    render(<ShelfReviewButtons ps={ps()} onDone={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Reject ICT_PS_AB12CD' }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('button', { name: 'Reject' })).toBeDisabled()
    await userEvent.type(within(dialog).getByLabelText(/remarks/i), 'Too broad')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Reject' }))
    await waitFor(() => expect(svc.proposalService.reviewFromShelf).toHaveBeenCalledWith(9, 'reject', 'Too broad'))
  })

  it('shows nothing for staff-made or already decided entries', () => {
    const { container, rerender } = render(<ShelfReviewButtons ps={ps({ proposal: undefined })} onDone={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
    rerender(<ShelfReviewButtons ps={ps({ proposal: { id: 4, status: 'approved', is_group: false, members: [] } })} onDone={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('mentor / lead changes the team', () => {
  const project = { id: 7, batch: { id: 2, code: 'B1' }, members: [
    { student_id: 1, name: 'Asha', role: 'Team Lead', is_lead: true }, { student_id: 2, name: 'Bina', role: 'Tester', is_lead: false }] }

  it('lists only free batch students, edits roles and saves in one go', async () => {
    svc.studentService.list.mockResolvedValue({ items: [
      { id: 1, name: 'Asha', registration_no: 'R1', project: { id: 7 } }, { id: 2, name: 'Bina', registration_no: 'R2', project: { id: 7 } },
      { id: 3, name: 'Chitra', registration_no: 'R3', project: null }, { id: 4, name: 'Dev', registration_no: 'R4', project: { id: 99 } }] })
    svc.projectService.setMembers.mockResolvedValue({})
    const onSaved = vi.fn()
    render(<ProjectTeamModal project={project} onClose={vi.fn()} onSaved={onSaved} />)
    await screen.findByLabelText('Select Chitra')
    expect(screen.queryByLabelText('Select Dev')).not.toBeInTheDocument()                    // has another project
    await userEvent.click(screen.getByLabelText('Select Bina'))                                // remove Bina
    await userEvent.click(screen.getByLabelText('Select Chitra'))
    await userEvent.type(screen.getByLabelText('Role of Chitra'), 'Frontend')
    await userEvent.click(screen.getByRole('button', { name: 'Save team' }))
    await waitFor(() => expect(svc.projectService.setMembers).toHaveBeenCalled())
    expect(svc.projectService.setMembers.mock.calls[0].slice(0, 2)).toEqual([7, [
      { student_id: 1, role: 'Team Lead', is_lead: true }, { student_id: 3, role: 'Frontend' }]])
    expect(onSaved).toHaveBeenCalled()
  })
})
