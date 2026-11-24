import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import UserManagement from './pages/admin/UserManagement'
import StudentManagement from './pages/admin/StudentManagement'
import { staffCredentialsCsv } from './utils/credentials'
import * as svc from './services/adminService'

vi.mock('./services/adminService', async () => {
  const actual = await vi.importActual('./services/adminService')
  return {
    ...actual,
    downloadTextFile: vi.fn(),
    domainService: { list: vi.fn() },
    batchService: { list: vi.fn() },
    studentService: { list: vi.fn(), credentials: vi.fn(), create: vi.fn() },
    userService: { list: vi.fn(), mentors: vi.fn(), credentials: vi.fn(), remove: vi.fn(), create: vi.fn(), setActive: vi.fn(), resetPassword: vi.fn() },
  }
})

const MENTOR = { id: 10, user_id: 20, name: 'Mia Mentor', email: 'mia@x.com', is_active: true, mentor_type: 'internal', designation: 'Trainer' }
const EMPTY = { items: [], meta: { page: 1, pages: 1, total: 0 } }

beforeEach(() => {
  vi.clearAllMocks()
  svc.domainService.list.mockResolvedValue([])
  svc.batchService.list.mockResolvedValue(EMPTY)
  svc.userService.mentors.mockResolvedValue({ items: [MENTOR], meta: { page: 1, pages: 1, total: 1 } })
  svc.userService.list.mockResolvedValue({ items: [{ id: 5, name: 'Lena Lead', email: 'lena@x.com', role: 'domain_lead', is_active: true }], meta: { page: 1, pages: 1, total: 1 } })
})

describe('staff credentials file', () => {
  it('has one row per person with role, details and the temporary password, and neutralises formulas', () => {
    const csv = staffCredentialsCsv([{ name: '=cmd()', email: 'a@x.com', temporary_password: 'Tmp1', role: 'mentor', designation: 'CTO', company: 'Acme', details: 'Industry mentor', phone: '99' }], 'https://app.test')
    expect(csv).toContain('Temporary password')
    expect(csv).toContain('"Mentor"')
    expect(csv).toContain('"Acme"')
    expect(csv).toContain('"https://app.test"')
    expect(csv).toContain(`"'=cmd()"`)
  })
})

describe('mentors page – credentials and delete', () => {
  const renderMentors = () => render(<MemoryRouter><UserManagement fixedRole="mentor" title="Mentors" addLabel="Add mentor" /></MemoryRouter>)

  it('generates and offers a credentials download for mentors', async () => {
    svc.userService.credentials.mockResolvedValue({
      credentials: [{ name: 'Mia Mentor', email: 'mia@x.com', temporary_password: 'Zz12345678', role: 'mentor', designation: 'Trainer', company: '', details: 'Internal mentor', phone: '' }],
      skipped: [{ name: 'Old Mentor', email: 'old@x.com', reason: 'Already set their own password' }], role: 'mentor',
    })
    renderMentors()
    await userEvent.click(await screen.findByRole('button', { name: /download credentials/i }))
    const dialog = screen.getByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: /generate passwords/i }))
    await waitFor(() => expect(svc.userService.credentials).toHaveBeenCalledWith('mentor', undefined, false))
    expect(await within(dialog).findByText(/1 mentor\(s\) ready\. 1 skipped\./)).toBeInTheDocument()
    expect(within(dialog).getByLabelText('Skipped users')).toHaveTextContent('Old Mentor (old@x.com) – Already set their own password')
    await userEvent.click(within(dialog).getByRole('button', { name: /download details with passwords/i }))
    expect(svc.downloadTextFile).toHaveBeenCalledWith(expect.stringContaining('Zz12345678'), 'mentor_credentials.csv')
  })

  it('asks for confirmation before deleting (using the user id, not the mentor id)', async () => {
    svc.userService.remove.mockResolvedValue({})
    renderMentors()
    await userEvent.click(await screen.findByRole('button', { name: 'Delete Mia Mentor' }))
    expect(svc.userService.remove).not.toHaveBeenCalled()
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /delete permanently/i }))
    await waitFor(() => expect(svc.userService.remove).toHaveBeenCalledWith(20))
  })

  it('shows the server reason when a delete is refused', async () => {
    svc.userService.remove.mockRejectedValue({ response: { status: 409, data: { message: 'This mentor is assigned to 1 batch(es) and 0 project(s). Reassign or remove them first.' } } })
    renderMentors()
    await userEvent.click(await screen.findByRole('button', { name: 'Delete Mia Mentor' }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /delete permanently/i }))
    expect(await screen.findByText(/reassign or remove them first/i)).toBeInTheDocument()
  })
})

describe('credentials – reissue for people who already set a password', () => {
  it('sends include_active only when the box is ticked', async () => {
    svc.userService.credentials.mockResolvedValue({ credentials: [], skipped: [], role: 'mentor' })
    render(<MemoryRouter><UserManagement fixedRole="mentor" title="Mentors" addLabel="Add mentor" /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button', { name: /download credentials/i }))
    const dialog = screen.getByRole('dialog')
    await userEvent.click(within(dialog).getByRole('checkbox', { name: /current password stops working/i }))
    await userEvent.click(within(dialog).getByRole('button', { name: /generate passwords/i }))
    await waitFor(() => expect(svc.userService.credentials).toHaveBeenCalledWith('mentor', undefined, true))
  })

  it("offers a download right after resetting one person's password", async () => {
    svc.userService.resetPassword.mockResolvedValue({ temporary_password: 'Reset12345' })
    render(<MemoryRouter><UserManagement fixedRole="mentor" title="Mentors" addLabel="Add mentor" /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button', { name: /reset password/i }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^reset password$/i }))
    await userEvent.click(await screen.findByRole('button', { name: /download login details/i }))
    expect(svc.downloadTextFile).toHaveBeenCalledWith(expect.stringContaining('Reset12345'), 'mia_login_details.csv')
  })
})

describe('domain leads page', () => {
  it('offers credentials for domain leads too', async () => {
    svc.userService.credentials.mockResolvedValue({ credentials: [], skipped: [], role: 'domain_lead' })
    render(<MemoryRouter><UserManagement fixedRole="domain_lead" title="Domain Leads" addLabel="Add domain lead" /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button', { name: /download credentials/i }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /generate passwords/i }))
    await waitFor(() => expect(svc.userService.credentials).toHaveBeenCalledWith('domain_lead', undefined, false))
  })
})

describe('students page – delete', () => {
  it('deletes by the student\'s user id after confirmation', async () => {
    svc.studentService.list.mockResolvedValue({ items: [{ id: 3, user_id: 33, name: 'Asha K', email: 'asha@x.com', registration_no: 'R1', batch: { code: 'B1' }, phone: '' }], meta: { page: 1, pages: 1, total: 1 } })
    svc.userService.remove.mockResolvedValue({})
    render(<MemoryRouter><StudentManagement /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button', { name: 'Delete Asha K' }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /delete permanently/i }))
    await waitFor(() => expect(svc.userService.remove).toHaveBeenCalledWith(33))
  })
})

describe('domain leads page – domains', () => {
  const lead = (domains) => ({ id: 5, name: 'Lena Lead', email: 'lena@x.com', role: 'domain_lead', is_active: true, domains })
  const renderLeads = () => render(<MemoryRouter><UserManagement fixedRole="domain_lead" title="Domain Leads" addLabel="Add domain lead" /></MemoryRouter>)

  it('warns when a lead has no domain and lets the admin assign one', async () => {
    svc.userService.list.mockResolvedValue({ items: [lead([])], meta: { page: 1, pages: 1, total: 1 } })
    svc.domainService.list.mockResolvedValue([{ id: 1, name: 'Enterprise Domain' }, { id: 2, name: 'IoT' }])
    svc.userService.setDomains = vi.fn().mockResolvedValue({})
    renderLeads()
    expect(await screen.findByText(/no domain – sees nothing/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /^domains$/i }))
    const dialog = screen.getByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: /^save$/i }))
    expect(await within(dialog).findByText(/choose at least one domain/i)).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('checkbox', { name: 'Enterprise Domain' }))
    await userEvent.click(within(dialog).getByRole('button', { name: /^save$/i }))
    await waitFor(() => expect(svc.userService.setDomains).toHaveBeenCalledWith(5, [1]))
  })

  it('shows the domains a lead already leads', async () => {
    svc.userService.list.mockResolvedValue({ items: [lead([{ id: 1, name: 'Enterprise Domain' }])], meta: { page: 1, pages: 1, total: 1 } })
    renderLeads()
    expect(await screen.findByText('Enterprise Domain')).toBeInTheDocument()
    expect(screen.queryByText(/sees nothing/i)).not.toBeInTheDocument()
  })
})
