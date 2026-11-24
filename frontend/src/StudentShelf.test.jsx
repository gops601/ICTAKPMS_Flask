import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import UserManagement from './pages/admin/UserManagement'
import MyProposal from './pages/student/MyProposal'
import ProposalApprovals from './pages/mentor/ProposalApprovals'
import * as svc from './services/adminService'

vi.mock('./services/adminService', async () => {
  const actual = await vi.importActual('./services/adminService')
  return {
    ...actual,
    downloadTextFile: vi.fn(),
    domainService: { list: vi.fn() },
    userService: { list: vi.fn(), mentors: vi.fn(), create: vi.fn(), credentials: vi.fn(), remove: vi.fn(), setActive: vi.fn(), resetPassword: vi.fn() },
    proposalService: { mine: vi.fn(), list: vi.fn(), submit: vi.fn(), review: vi.fn(), download: vi.fn(), downloadDataset: vi.fn(), dataTemplate: vi.fn().mockResolvedValue(), projectTemplate: vi.fn().mockResolvedValue() },
  }
})

const DOMAINS = [{ id: 1, name: 'AI & ML' }, { id: 2, name: 'IoT' }]
const EMPTY = { items: [], meta: { page: 1, pages: 1, total: 0 } }

beforeEach(() => {
  vi.clearAllMocks()
  svc.domainService.list.mockResolvedValue(DOMAINS)
  svc.userService.list.mockResolvedValue(EMPTY)
  svc.userService.mentors.mockResolvedValue(EMPTY)
})

describe('domain lead is asked for the domain', () => {
  const open = async (props) => {
    render(<MemoryRouter><UserManagement {...props} /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button', { name: /add domain lead|add mentor/i }))
    return screen.getByRole('dialog')
  }

  it('requires at least one domain and sends the chosen domains', async () => {
    svc.userService.create.mockResolvedValue({ email: 'l@x.com', temporary_password: 'Tmp1' })
    const dialog = await open({ fixedRole: 'domain_lead', title: 'Domain Leads', addLabel: 'Add domain lead' })
    await userEvent.type(within(dialog).getByLabelText(/^name/i), 'Lena Lead')
    await userEvent.type(within(dialog).getByLabelText(/^email/i), 'l@x.com')
    await userEvent.click(within(dialog).getByRole('button', { name: /create user/i }))
    expect(await within(dialog).findByText(/choose the domain this lead will manage/i)).toBeInTheDocument()
    expect(svc.userService.create).not.toHaveBeenCalled()
    await userEvent.click(within(dialog).getByRole('checkbox', { name: 'AI & ML' }))
    await userEvent.click(within(dialog).getByRole('checkbox', { name: 'IoT' }))
    await userEvent.click(within(dialog).getByRole('button', { name: /create user/i }))
    await waitFor(() => expect(svc.userService.create).toHaveBeenCalled())
    expect(svc.userService.create.mock.calls[0][0]).toMatchObject({ role: 'domain_lead', domain_ids: [1, 2] })
  })

  it('mentors are created under a domain', async () => {
    const dialog = await open({ fixedRole: 'mentor', title: 'Mentors', addLabel: 'Add mentor' })
    expect(within(dialog).getByLabelText(/^domain/i)).toBeRequired()
  })
})

describe('student uploads a project with datasets', () => {
  const INFO = { proposals: [], can_upload: true, has_project: false, blocked_reason: null, domain: { id: 1, name: 'AI & ML' }, subdomains: [{ id: 5, name: 'Vision' }] }
  const file = (name) => new File(['x'], name, { type: 'text/plain' })

  it('offers the same project template the Project Shelf uses', async () => {
    svc.proposalService.mine.mockResolvedValue(INFO)
    render(<MyProposal />)
    const box = await screen.findByLabelText(/sample project template/i)
    await userEvent.click(within(box).getByRole('button', { name: /excel/i }))
    await userEvent.click(within(box).getByRole('button', { name: /csv/i }))
    expect(svc.proposalService.projectTemplate.mock.calls).toEqual([['xlsx'], ['csv']])
  })

  it('offers the Excel template and insists on the data sheet when datasets are attached', async () => {
    svc.proposalService.mine.mockResolvedValue(INFO)
    render(<MyProposal />)
    await userEvent.click(await screen.findByRole('button', { name: /download excel template/i }))
    expect(svc.proposalService.dataTemplate).toHaveBeenCalled()
    await userEvent.type(screen.getByLabelText(/^title/i), 'Leaf scanner')
    await userEvent.selectOptions(screen.getByLabelText(/^subdomain/i), '5')
    await userEvent.upload(screen.getByLabelText(/detailed project proposal/i), file('detail.pdf'))
    await userEvent.upload(screen.getByLabelText(/^datasets/i), [file('a.csv')])
    await userEvent.click(screen.getByRole('button', { name: /submit for approval/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/filled data collection sheet/i)
    expect(svc.proposalService.submit).not.toHaveBeenCalled()
  })

  it('sends the document, every dataset and the subdomain', async () => {
    svc.proposalService.mine.mockResolvedValue(INFO)
    svc.proposalService.submit.mockResolvedValue({})
    render(<MyProposal />)
    await userEvent.type(await screen.findByLabelText(/^title/i), 'Leaf scanner')
    await userEvent.selectOptions(screen.getByLabelText(/^subdomain/i), '5')
    await userEvent.upload(screen.getByLabelText(/detailed project proposal/i), file('detail.pdf'))
    await userEvent.upload(screen.getByLabelText(/^datasets/i), [file('a.csv'), file('b.csv')])
    await userEvent.upload(screen.getByLabelText(/data collection sheet/i), file('sheet.xlsx'))
    await userEvent.click(screen.getByRole('button', { name: /submit for approval/i }))
    await waitFor(() => expect(svc.proposalService.submit).toHaveBeenCalled())
    const [title, , doc, datasets, sub, sheet] = svc.proposalService.submit.mock.calls[0]
    expect(sheet.name).toBe('sheet.xlsx')
    expect(title).toBe('Leaf scanner')
    expect(doc.name).toBe('detail.pdf')
    expect(datasets.map((f) => f.name)).toEqual(['a.csv', 'b.csv'])
    expect(sub).toBe('5')
  })

  it('shows the shelf ID once the project is approved', async () => {
    svc.proposalService.mine.mockResolvedValue({ ...INFO, can_upload: false, blocked_reason: 'Your project has already been approved and is on the Project Shelf.',
      proposals: [{ id: 1, title: 'Leaf scanner', status: 'approved', remarks: null, file: { name: 'detail.pdf' }, datasets: [{ id: 1, name: 'a.csv' }], subdomain: { name: 'Vision' }, shelf: { id: 9, ps_code: 'ICT_PS_AB12CD' }, submitted_at: '2026-11-23T10:00:00' }] })
    render(<MyProposal />)
    expect(await screen.findByText(/on the project shelf as ICT_PS_AB12CD/i)).toBeInTheDocument()
    expect(screen.getByText(/1 dataset\(s\)/)).toBeInTheDocument()
  })
})

describe('mentor sees the datasets of a student project', () => {
  it('lists dataset downloads in the approval queue', async () => {
    svc.proposalService.list.mockResolvedValue({ items: [{ id: 3, title: 'Leaf scanner', summary: 's', status: 'pending', subdomain: { name: 'Vision' }, file: { name: 'd.pdf' }, datasets: [{ id: 7, name: 'leaves.csv' }], shelf: null, student: { name: 'Asha', registration_no: 'R1', batch: { code: 'B1' } } }], meta: { page: 1, pages: 1, total: 1 } })
    svc.proposalService.downloadDataset.mockResolvedValue()
    render(<MemoryRouter><ProposalApprovals /></MemoryRouter>)
    const list = await screen.findByLabelText('Datasets of Leaf scanner')
    await userEvent.click(within(list).getByRole('button', { name: 'leaves.csv' }))
    expect(svc.proposalService.downloadDataset).toHaveBeenCalledWith(expect.objectContaining({ id: 3 }), expect.objectContaining({ id: 7 }))
    expect(screen.getByText(/Subdomain: Vision/)).toBeInTheDocument()
  })
})
