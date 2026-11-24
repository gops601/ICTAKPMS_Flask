import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AppLayout from './layouts/AppLayout'

let mockUser
vi.mock('./context/AuthContext', () => ({ useAuth: () => ({ user: mockUser, logout: vi.fn() }) }))
vi.mock('./components/NotificationBell', () => ({ default: () => null }))

const renderLayout = () => render(
  <MemoryRouter initialEntries={['/lead']}><Routes><Route element={<AppLayout />}><Route path="/lead" element={<div>page</div>} /></Route></Routes></MemoryRouter>,
)
beforeEach(() => { mockUser = { id: 1, name: 'Lena', email: 'l@x.com', role: 'domain_lead', domains: [] } })

describe('domain lead without a domain', () => {
  it('is told why nothing shows up', () => {
    renderLayout()
    expect(screen.getByRole('alert')).toHaveTextContent(/not been assigned to a domain/i)
  })
  it('sees no warning once a domain is assigned', () => {
    mockUser = { ...mockUser, domains: [{ id: 1, name: 'Enterprise Domain' }] }
    renderLayout()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
