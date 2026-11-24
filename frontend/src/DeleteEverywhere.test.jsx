import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import DomainManagement from './pages/admin/DomainManagement'
import OUManagement from './pages/admin/OUManagement'
import ProblemStatementList from './pages/domain_lead/ProblemStatementList'
import * as svc from './services/adminService'

vi.mock('./hooks/useBasePath', () => ({ default: () => '/lead' }))
vi.mock('./services/adminService', async () => {
  const actual = await vi.importActual('./services/adminService')
  return {
    ...actual,
    ouService: { list: vi.fn(), remove: vi.fn(), fields: vi.fn() },
    domainService: { list: vi.fn(), remove: vi.fn(), removeSubdomain: vi.fn() },
    psService: { list: vi.fn(), remove: vi.fn(), industries: vi.fn().mockResolvedValue([]), setStatus: vi.fn() },
    userService: { list: vi.fn() },
  }
})

const meta = { page: 1, pages: 1, total: 1 }
beforeEach(() => vi.clearAllMocks())

describe('delete buttons on the remaining admin pages', () => {
  it('Project Shelf: confirms, deletes, and shows why when refused', async () => {
    svc.domainService.list.mockResolvedValue([])
    svc.psService.list.mockResolvedValue({ items: [{ id: 3, ps_code: 'ICT_PS_AB12CD', title: 'Chatbot', domain: { id: 1, name: 'AI' }, difficulty: 'easy', source_type: 'internal', dataset_count: 0, document_count: 0, status: 'active' }], meta })
    svc.psService.remove.mockRejectedValueOnce({ response: { status: 409, data: { message: '2 project(s) were allocated from this entry. Deactivate it instead of deleting.' } } })
    svc.psService.remove.mockResolvedValueOnce({})
    render(<MemoryRouter><ProblemStatementList /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button', { name: 'Delete ICT_PS_AB12CD' }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /delete permanently/i }))
    expect(await screen.findByText(/deactivate it instead of deleting/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Delete ICT_PS_AB12CD' }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /delete permanently/i }))
    await waitFor(() => expect(svc.psService.remove).toHaveBeenCalledTimes(2))
  })

  it('Domains: delete a domain and a subdomain', async () => {
    svc.domainService.list.mockResolvedValue([{ id: 1, name: 'AI & ML', code: 'AIML', is_active: true, leads: [], batch_count: 0, student_count: 0, subdomains: [{ id: 5, domain_id: 1, name: 'NLP', is_active: true }] }])
    svc.domainService.remove.mockResolvedValue({})
    svc.domainService.removeSubdomain.mockResolvedValue({})
    render(<MemoryRouter><DomainManagement /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button', { name: 'Delete AI & ML' }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /delete permanently/i }))
    await waitFor(() => expect(svc.domainService.remove).toHaveBeenCalledWith(1))
    await userEvent.click(await screen.findByRole('button', { name: /^subdomains$/i }))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    await userEvent.click(await screen.findByRole('button', { name: 'Delete subdomain NLP' }))
    await waitFor(() => expect(svc.domainService.removeSubdomain).toHaveBeenCalledWith(5))
  })

  it('OUs: delete an OU after confirmation', async () => {
    svc.ouService.list.mockResolvedValue([{ id: 2, name: 'Retail', code: 'RETAIL', is_active: true }])
    svc.ouService.remove.mockResolvedValue({})
    render(<MemoryRouter><OUManagement /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button', { name: 'Delete Retail' }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /delete permanently/i }))
    await waitFor(() => expect(svc.ouService.remove).toHaveBeenCalledWith(2))
  })
})
