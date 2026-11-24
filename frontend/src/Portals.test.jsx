import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PortalConnections from './pages/admin/PortalConnections'
import SsoCallback from './pages/common/SsoCallback'
import DataCollectionTable from './components/DataCollectionTable'
import * as svc from './services/adminService'
import api from './services/api'

const refreshUser = vi.fn().mockResolvedValue()
vi.mock('./context/AuthContext', () => ({ useAuth: () => ({ user: null, refreshUser }) }))
vi.mock('./services/adminService', async () => {
  const actual = await vi.importActual('./services/adminService')
  return {
    ...actual,
    portalService: { list: vi.fn(), create: vi.fn(), update: vi.fn(), sync: vi.fn(), rotateSecret: vi.fn(), remove: vi.fn(), guide: vi.fn().mockResolvedValue(), config: vi.fn().mockResolvedValue() },
    ouService: { list: vi.fn().mockResolvedValue({ items: [{ id: 1, name: 'ICTAK' }] }) },
  }
})

const PORTAL = {
  id: 1, name: 'ICTAK Learn', slug: 'ictak-learn', base_url: 'https://learn.example.org', is_active: true, has_api_token: true, batch_count: 2,
  last_sync_at: '2026-11-20T10:00:00',
  last_sync_summary: { batches_created: 1, batches_updated: 0, students_created: 3, students_updated: 0, problems: ['Batch X: domain missing'] },
  push_endpoint: 'http://h/api/integrations/ictak-learn/enrollments', sso_login_url: 'http://h/sso?portal=ictak-learn&token=<signed-token>',
}

beforeEach(() => { vi.clearAllMocks(); svc.portalService.list.mockResolvedValue([PORTAL]) })

describe('portal connections (admin)', () => {
  it('lists portals with their endpoints and last sync problems, and syncs now', async () => {
    svc.portalService.sync.mockResolvedValue({ ...PORTAL, last_sync_summary: { batches_created: 2, batches_updated: 0, students_created: 8, students_updated: 0, problems: [] } })
    render(<PortalConnections />)
    const card = await screen.findByRole('region', { name: 'ICTAK Learn' })
    expect(within(card).getByText(/integrations\/ictak-learn\/enrollments/)).toBeInTheDocument()
    expect(within(card).getByText('Batch X: domain missing')).toBeInTheDocument()
    await userEvent.click(within(card).getByRole('button', { name: /sync now/i }))
    expect(await screen.findByText(/2 new batch\(es\), 8 new student\(s\)/)).toBeInTheDocument()
  })

  it('shows the shared secret once after connecting a portal', async () => {
    svc.portalService.list.mockResolvedValue([])
    svc.portalService.create.mockResolvedValue({ ...PORTAL, shared_secret: 'S3CRET-VALUE', sso_endpoint: 'http://h/api/auth/sso' })
    render(<PortalConnections />)
    await userEvent.click(await screen.findByRole('button', { name: /connect a portal/i }))
    await userEvent.type(screen.getByLabelText(/portal name/i), 'ICTAK Learn')
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))
    expect(await screen.findByText('S3CRET-VALUE')).toBeInTheDocument()
    expect(screen.getByText(/shown only now/i)).toBeInTheDocument()
    expect(svc.portalService.create).toHaveBeenCalledWith(expect.objectContaining({ name: 'ICTAK Learn' }))
  })
})

describe('documentation and configuration file', () => {
  it('downloads the guide, links the API docs, and offers the config file with the one-time secret', async () => {
    svc.portalService.create.mockResolvedValue({ ...PORTAL, shared_secret: 'S3CRET-VALUE', sso_endpoint: 'http://h/api/auth/sso' })
    render(<PortalConnections />)
    expect(await screen.findByRole('link', { name: /api documentation/i })).toHaveAttribute('href', '/api/docs')
    await userEvent.click(screen.getByRole('button', { name: /integration guide/i }))
    expect(svc.portalService.guide).toHaveBeenCalled()
    await userEvent.click(await screen.findByRole('button', { name: /download configuration for ICTAK Learn/i }))
    expect(svc.portalService.config).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }), 'json')
    await userEvent.click(screen.getByRole('button', { name: /connect a portal/i }))
    await userEvent.type(screen.getByLabelText(/portal name/i), 'X Portal')
    await userEvent.click(screen.getByRole('button', { name: /^save$/i }))
    await userEvent.click(await screen.findByRole('button', { name: /\.env file \(with secret\)/i }))
    expect(svc.portalService.config).toHaveBeenLastCalledWith(expect.anything(), 'env', 'S3CRET-VALUE')
  })
})

describe('SSO landing page', () => {
  const renderSso = (url) => render(
    <MemoryRouter initialEntries={[url]}>
      <Routes><Route path="/sso" element={<SsoCallback />} /><Route path="/student" element={<div>student home</div>} /></Routes>
    </MemoryRouter>)

  it('exchanges the portal token for a session and goes to the role home', async () => {
    const post = vi.spyOn(api, 'post').mockResolvedValue({ data: { data: { access_token: 'a', refresh_token: 'r', user: { role: 'student' } } } })
    renderSso('/sso?portal=ictak-learn&token=abc')
    expect(await screen.findByText('student home')).toBeInTheDocument()
    expect(post).toHaveBeenCalledWith('/auth/sso', { portal: 'ictak-learn', token: 'abc' })
    expect(refreshUser).toHaveBeenCalled()
  })

  it('explains a failed sign-in', async () => {
    vi.spyOn(api, 'post').mockRejectedValue({ response: { status: 401, data: { message: 'Single sign-on failed. Ask the portal to retry.' } } })
    renderSso('/sso?portal=x&token=bad')
    expect(await screen.findByRole('alert')).toHaveTextContent(/single sign-on failed/i)
  })

  it('rejects an incomplete link', async () => {
    renderSso('/sso?portal=x')
    expect(await screen.findByRole('alert')).toHaveTextContent(/incomplete/i)
  })
})

describe('data collection view', () => {
  it('shows each dataset with its details', () => {
    render(<DataCollectionTable rows={[{ name: 'Leaf images', description: 'Photos', source: 'Own collection', data_type: 'Image', records: 5000, features: 3, feature_names: 'id, label', personal_data: 'No', limitations: 'Daylight only' }]} />)
    expect(screen.getByText('Leaf images')).toBeInTheDocument()
    expect(screen.getByText('5000')).toBeInTheDocument()
    expect(screen.getByText(/Daylight only/)).toBeInTheDocument()
  })

  it('renders nothing without rows', () => {
    const { container } = render(<DataCollectionTable rows={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
