import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BatchList from './pages/admin/BatchList'
import * as svc from './services/adminService'

vi.mock('./services/adminService', async () => {
  const actual = await vi.importActual('./services/adminService')
  return {
    ...actual,
    ouService: { list: vi.fn().mockResolvedValue([]) },
    domainService: { list: vi.fn().mockResolvedValue([]) },
    reportService: { batchDetailed: vi.fn() },
    batchService: { list: vi.fn(), remove: vi.fn(), setStatus: vi.fn() },
  }
})

const batch = (over = {}) => ({ id: 4, code: 'ICT_AIML_AB12CD', name: 'Batch Four', ou: { id: 1, name: 'OU' }, domain: { id: 1, name: 'AI' }, start_date: null, student_count: 0, status: 'active', ...over })
const list = (items) => svc.batchService.list.mockResolvedValue({ items, meta: { page: 1, pages: 1, total: items.length } })
const renderPage = () => render(<MemoryRouter><BatchList /></MemoryRouter>)

beforeEach(() => vi.clearAllMocks())

describe('batches – delete', () => {
  it('confirms, then deletes an empty batch', async () => {
    list([batch()])
    svc.batchService.remove.mockResolvedValue({})
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: 'Delete batch ICT_AIML_AB12CD' }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).queryByRole('checkbox')).not.toBeInTheDocument()          // no students: nothing extra to choose
    expect(svc.batchService.remove).not.toHaveBeenCalled()
    await userEvent.click(within(dialog).getByRole('button', { name: /delete permanently/i }))
    await waitFor(() => expect(svc.batchService.remove).toHaveBeenCalledWith(4, false))
  })

  it('offers to delete the students too, only when the batch has some', async () => {
    list([batch({ student_count: 12 })])
    svc.batchService.remove.mockResolvedValue({})
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: /delete batch/i }))
    const dialog = screen.getByRole('dialog')
    await userEvent.click(within(dialog).getByRole('checkbox', { name: /also delete its 12 student/i }))
    await userEvent.click(within(dialog).getByRole('button', { name: /delete permanently/i }))
    await waitFor(() => expect(svc.batchService.remove).toHaveBeenCalledWith(4, true))
  })

  it('shows the server reason when the batch cannot be deleted', async () => {
    list([batch()])
    svc.batchService.remove.mockRejectedValue({ response: { status: 409, data: { message: 'This batch has 3 project(s). Close the batch instead of deleting it.' } } })
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: /delete batch/i }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /delete permanently/i }))
    expect(await screen.findByText(/close the batch instead/i)).toBeInTheDocument()
  })
})
