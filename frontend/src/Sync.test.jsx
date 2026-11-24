import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useList } from './hooks/useList'
import MyProjectGate from './components/MyProjectGate'
import ProblemStatementList from './pages/domain_lead/ProblemStatementList'
import * as svc from './services/adminService'

vi.mock('./hooks/useBasePath', () => ({ default: () => '/lead' }))
vi.mock('./services/adminService', async () => {
  const actual = await vi.importActual('./services/adminService')
  return {
    ...actual,
    domainService: { list: vi.fn().mockResolvedValue([]) },
    psService: { list: vi.fn(), industries: vi.fn().mockResolvedValue([]), setStatus: vi.fn(), remove: vi.fn() },
    projectService: { list: vi.fn() },
    proposalService: { mine: vi.fn() },
  }
})

beforeEach(() => vi.clearAllMocks())

function Probe({ fetcher }) {
  const { items } = useList(fetcher, {})
  return <div data-testid="n">{items.length}</div>
}

describe('lists stay in sync with other roles', () => {
  it('refetches when the tab becomes visible again', async () => {
    const fetcher = vi.fn().mockResolvedValue({ items: [1], meta: {} })
    render(<Probe fetcher={fetcher} />)
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1))
    fetcher.mockResolvedValue({ items: [1, 2], meta: {} })
    await act(async () => { window.dispatchEvent(new Event('focus')) })
    await waitFor(() => expect(screen.getByTestId('n')).toHaveTextContent('2'))
    expect(fetcher).toHaveBeenCalledTimes(2)
  })
})

describe('project shelf – approval', () => {
  const row = (over = {}) => ({ id: 3, ps_code: 'ICT_PS_AB12CD', title: 'Leaf scanner', domain: { id: 1, name: 'AI' }, difficulty: 'easy', source_type: 'internal', dataset_count: 2, document_count: 1, status: 'active', approval_status: 'pending', proposed_by: { id: 1, name: 'Asha' }, ...over })

  it('marks student projects awaiting approval and can filter by approval', async () => {
    svc.psService.list.mockResolvedValue({ items: [row()], meta: { page: 1, pages: 1, total: 1 } })
    render(<MemoryRouter><ProblemStatementList /></MemoryRouter>)
    expect(await screen.findByText('Awaiting mentor approval', { selector: 'span' })).toBeInTheDocument()
    expect(screen.getByText(/Student project · Asha/)).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText('Filter by approval'), 'pending')
    await waitFor(() => expect(svc.psService.list).toHaveBeenLastCalledWith(expect.objectContaining({ approval_status: 'pending' })))
  })
})

describe('student with a pending project', () => {
  it('is told the SRS opens once the mentor approves', async () => {
    svc.projectService.list.mockResolvedValue({ items: [], meta: {} })
    svc.proposalService.mine.mockResolvedValue({ proposals: [{ id: 1, title: 'Leaf scanner', status: 'pending' }] })
    render(<MemoryRouter><MyProjectGate title="SRS">{() => <div>project</div>}</MyProjectGate></MemoryRouter>)
    expect(await screen.findByText(/awaiting your mentor's approval/i)).toBeInTheDocument()
    expect(screen.getByText(/SRS opens as soon as your mentor approves/i)).toBeInTheDocument()
  })

  it('offers to add their own project when nothing is pending', async () => {
    svc.projectService.list.mockResolvedValue({ items: [], meta: {} })
    svc.proposalService.mine.mockResolvedValue({ proposals: [] })
    render(<MemoryRouter><MyProjectGate title="SRS">{() => <div>project</div>}</MyProjectGate></MemoryRouter>)
    expect(await screen.findByRole('link', { name: /add your own project/i })).toHaveAttribute('href', '/student/proposal')
  })
})
