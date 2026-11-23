import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MyProposal from './pages/student/MyProposal'

const mine = vi.hoisted(() => vi.fn())
vi.mock('./services/adminService', async (orig) => ({
  ...(await orig()),
  proposalService: { mine, submit: vi.fn(), download: vi.fn() },
}))

beforeEach(() => vi.clearAllMocks())

describe('student problem statement upload', () => {
  it('is disabled with an explanation once a project is allocated', async () => {
    mine.mockResolvedValue({ proposals: [], can_upload: false, has_project: true, blocked_reason: 'A project has already been allocated to you.' })
    render(<MyProposal />)
    expect(await screen.findByText(/project has already been allocated/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/^Title/)).toBeDisabled()
    expect(screen.getByRole('button', { name: /submit for approval/i })).toBeDisabled()
  })

  it('is enabled when the student has no project', async () => {
    mine.mockResolvedValue({ proposals: [], can_upload: true, has_project: false, blocked_reason: null })
    render(<MyProposal />)
    await waitFor(() => expect(screen.getByLabelText(/^Title/)).toBeEnabled())
    expect(screen.getByRole('button', { name: /submit for approval/i })).toBeEnabled()
  })
})
