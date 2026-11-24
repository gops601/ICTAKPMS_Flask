import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AppLayout from './layouts/AppLayout'
import UserManagement from './pages/admin/UserManagement'
import * as svc from './services/adminService'

let mockUser
vi.mock('./context/AuthContext', () => ({ useAuth: () => ({ user: mockUser, logout: vi.fn(), refreshUser: vi.fn() }) }))
vi.mock('./services/adminService', async () => {
  const actual = await vi.importActual('./services/adminService')
  return {
    ...actual,
    userService: { list: vi.fn(), mentors: vi.fn(), setActive: vi.fn(), remove: vi.fn(), resetPassword: vi.fn(), credentials: vi.fn(), setDomains: vi.fn(), create: vi.fn() },
    domainService: { list: vi.fn().mockResolvedValue([]) },
    notificationService: { unreadCount: vi.fn().mockResolvedValue(0), list: vi.fn().mockResolvedValue({ items: [], meta: {} }) },
  }
})

beforeEach(() => vi.clearAllMocks())

describe('a domain lead is also a mentor', () => {
  const renderLayout = () => render(<MemoryRouter><AppLayout /></MemoryRouter>)

  it('adds Proposal Approvals to the lead menu when the lead has a mentor profile', () => {
    mockUser = { id: 1, name: 'Lea', role: 'domain_lead', is_mentor: true, domains: [{ id: 1, name: 'AI' }] }
    renderLayout()
    expect(screen.getAllByRole('link', { name: /proposal approvals/i }).length).toBeGreaterThan(0)
  })

  it('does not for a lead without a mentor profile', () => {
    mockUser = { id: 1, name: 'Lea', role: 'domain_lead', is_mentor: false, domains: [{ id: 1, name: 'AI' }] }
    renderLayout()
    expect(screen.queryByRole('link', { name: /proposal approvals/i })).not.toBeInTheDocument()
  })

  it('lists leads in the admin Mentors page with a Domain lead badge', async () => {
    mockUser = { id: 9, name: 'Ada', role: 'admin' }
    svc.userService.mentors.mockResolvedValue({ items: [
      { id: 1, user_id: 11, name: 'Mia Mentor', email: 'm@x.com', is_active: true, mentor_type: 'internal', is_domain_lead: false },
      { id: 2, user_id: 12, name: 'Lea Lead', email: 'l@x.com', is_active: true, mentor_type: 'internal', is_domain_lead: true },
    ], meta: { page: 1, pages: 1, total: 2 } })
    render(<MemoryRouter><UserManagement fixedRole="mentor" title="Mentors" /></MemoryRouter>)
    const row = (await screen.findByText('Lea Lead')).closest('tr')
    expect(within(row).getByText('Domain lead')).toBeInTheDocument()
    expect(within(screen.getByText('Mia Mentor').closest('tr')).queryByText('Domain lead')).not.toBeInTheDocument()
  })
})
