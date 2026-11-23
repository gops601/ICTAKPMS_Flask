import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { AuthProvider } from './context/AuthContext'
import api from './services/api'

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

const renderApp = (path = '/') =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider><App /></AuthProvider>
    </MemoryRouter>,
  )

const loginAs = (role) => {
  api.post.mockResolvedValueOnce({
    data: { data: { access_token: 'a', refresh_token: 'r',
      user: { id: 1, name: 'Test User', email: 't@x.com', role, must_change_password: false } } },
  })
}

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
})

describe('login', () => {
  it('redirects unauthenticated users to the login page', async () => {
    renderApp('/admin')
    expect(await screen.findByRole('heading', { name: /sign in/i })).toBeInTheDocument()
  })

  it('shows the server error on bad credentials', async () => {
    api.post.mockRejectedValueOnce({ response: { status: 401, data: { message: 'Invalid email or password' } } })
    renderApp('/login')
    await userEvent.type(screen.getByLabelText(/email/i), 'a@x.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'bad')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password')
  })

  it.each([
    ['admin', 'Administrator'],
    ['mentor', 'Mentor'],
    ['student', 'Student'],
    ['domain_lead', 'Domain Lead'],
  ])('logs in as %s and lands on the role home with role-labelled sidebar', async (role, label) => {
    loginAs(role)
    renderApp('/login')
    await userEvent.type(screen.getByLabelText(/email/i), 't@x.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'Passw0rd1')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))
    expect(await screen.findByText(/welcome, test user/i)).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: /main navigation/i })
    expect(nav).toBeInTheDocument()
    expect(screen.getAllByText(label).length).toBeGreaterThan(0)
  })
})

describe('role-based navigation', () => {
  it('sends a student away from admin routes', async () => {
    localStorage.setItem('plms_access', 'tok')
    api.get.mockResolvedValueOnce({ data: { data: { id: 2, name: 'Stu', email: 's@x.com', role: 'student', must_change_password: false } } })
    renderApp('/admin')
    await waitFor(() => expect(screen.getByText(/welcome, stu/i)).toBeInTheDocument())
    expect(screen.getByText('Student', { selector: 'div' })).toBeInTheDocument()
  })

  it('forces users with a temporary password to the change-password page after login', async () => {
    api.post.mockResolvedValueOnce({
      data: { data: { access_token: 'a', refresh_token: 'r',
        user: { id: 3, name: 'New', email: 'n@x.com', role: 'student', must_change_password: true } } },
    })
    renderApp('/login')
    await userEvent.type(screen.getByLabelText(/email/i), 'n@x.com')
    await userEvent.type(screen.getByLabelText(/password/i), 'Temp1234')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))
    expect(await screen.findByText(/must change your temporary password/i)).toBeInTheDocument()
  })
})
