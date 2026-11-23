import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProblemStatementForm from './pages/domain_lead/ProblemStatementForm'
import { SubdomainsModal } from './pages/admin/DomainManagement'
import * as svc from './services/adminService'

vi.mock('./hooks/useBasePath', () => ({ default: () => '/lead' }))
vi.mock('./services/adminService', async () => {
  const actual = await vi.importActual('./services/adminService')
  return {
    ...actual,
    domainService: { list: vi.fn(), addSubdomain: vi.fn(), updateSubdomain: vi.fn() },
    psService: { get: vi.fn(), create: vi.fn(), update: vi.fn(), industries: vi.fn(), upload: vi.fn(), removeFile: vi.fn(), download: vi.fn() },
  }
})

const AIML = { id: 1, name: 'AI & ML', is_active: true, subdomains: [{ id: 11, domain_id: 1, name: 'NLP', is_active: true }, { id: 12, domain_id: 1, name: 'Old', is_active: false }] }
const IOT = { id: 2, name: 'IoT', is_active: true, subdomains: [] }

beforeEach(() => {
  vi.clearAllMocks()
  svc.domainService.list.mockResolvedValue([AIML, IOT])
  svc.psService.industries.mockResolvedValue([])
})

const renderForm = () => render(
  <MemoryRouter initialEntries={['/lead/project-shelf/new']}>
    <Routes><Route path="/lead/project-shelf/new" element={<ProblemStatementForm />} /><Route path="*" element={<div>elsewhere</div>} /></Routes>
  </MemoryRouter>,
)

describe('project form – subdomain', () => {
  it('lists only active subdomains of the chosen domain and requires one', async () => {
    renderForm()
    const domain = await screen.findByLabelText(/^domain/i)
    const sub = screen.getByLabelText(/^subdomain/i)
    expect(sub).toBeDisabled()
    await userEvent.selectOptions(domain, '1')
    expect(sub).toBeEnabled()
    expect(sub).toBeRequired()
    expect(within(sub).getByRole('option', { name: 'NLP' })).toBeInTheDocument()
    expect(within(sub).queryByRole('option', { name: 'Old' })).not.toBeInTheDocument()   // inactive ones are hidden
  })

  it('is optional for a domain that has no subdomains yet', async () => {
    renderForm()
    await userEvent.selectOptions(await screen.findByLabelText(/^domain/i), '2')
    expect(screen.getByLabelText(/^subdomain/i)).not.toBeRequired()
  })

  it('lets the lead add a new subdomain on the spot and selects it', async () => {
    svc.domainService.addSubdomain.mockResolvedValue({ id: 13, domain_id: 1, name: 'Vision', is_active: true })
    renderForm()
    await userEvent.selectOptions(await screen.findByLabelText(/^domain/i), '1')
    await userEvent.type(screen.getByLabelText('New subdomain'), 'Vision')
    await userEvent.click(screen.getByRole('button', { name: /^add$/i }))
    await waitFor(() => expect(svc.domainService.addSubdomain).toHaveBeenCalledWith(1, 'Vision'))
    await waitFor(() => expect(screen.getByLabelText(/^subdomain/i)).toHaveValue('13'))
  })

  it('sends the chosen subdomain with the project', async () => {
    svc.psService.create.mockResolvedValue({ id: 9 })
    renderForm()
    await userEvent.type(await screen.findByLabelText(/project title/i), 'Chatbot')
    await userEvent.selectOptions(screen.getByLabelText(/^domain/i), '1')
    await userEvent.selectOptions(screen.getByLabelText(/^subdomain/i), '11')
    await userEvent.click(screen.getByRole('button', { name: /create & add files/i }))
    await waitFor(() => expect(svc.psService.create).toHaveBeenCalled())
    expect(svc.psService.create.mock.calls[0][0]).toMatchObject({ domain_id: 1, subdomain_id: 11, title: 'Chatbot' })
  })
})

describe('domains page – manage subdomains', () => {
  it('adds, renames and deactivates subdomains', async () => {
    svc.domainService.addSubdomain.mockResolvedValue({ id: 20, domain_id: 1, name: 'Vision', is_active: true })
    svc.domainService.updateSubdomain.mockImplementation((id, body) => Promise.resolve({ id, domain_id: 1, name: body.name ?? 'NLP', is_active: body.is_active ?? true }))
    render(<SubdomainsModal domain={AIML} onClose={vi.fn()} onChanged={vi.fn()} />)
    await userEvent.type(screen.getByLabelText('New subdomain name'), 'Vision')
    await userEvent.click(screen.getByRole('button', { name: /^add$/i }))
    expect(await screen.findByText('Vision')).toBeInTheDocument()
    await userEvent.click(screen.getAllByRole('button', { name: /rename/i })[0])
    const input = screen.getByLabelText(/^Rename /)
    await userEvent.clear(input)
    await userEvent.type(input, 'Language AI')
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await waitFor(() => expect(svc.domainService.updateSubdomain).toHaveBeenCalledWith(11, { name: 'Language AI' }))
    await userEvent.click(screen.getAllByRole('button', { name: /^deactivate$/i })[0])
    await waitFor(() => expect(svc.domainService.updateSubdomain).toHaveBeenCalledWith(expect.any(Number), { is_active: false }))
  })
})
