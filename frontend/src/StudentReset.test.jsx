import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StudentManagement from './pages/admin/StudentManagement'
import * as svc from './services/adminService'

vi.mock('./services/adminService', async () => {
  const actual = await vi.importActual('./services/adminService')
  return {
    ...actual,
    studentService: { list: vi.fn() },
    batchService: { list: vi.fn().mockResolvedValue({ items: [] }) },
    userService: { resetPassword: vi.fn(), remove: vi.fn() },
  }
})

beforeEach(() => vi.clearAllMocks())

describe('admin resets a student password', () => {
  it('confirms, resets by user id and shows the temporary password once', async () => {
    svc.studentService.list.mockResolvedValue({ items: [
      { id: 1, user_id: 41, name: 'Asha', email: 'asha@x.com', registration_no: 'ACADEMIC_ONLINE_0001', batch: { code: 'B1' }, phone: null },
    ], meta: { page: 1, pages: 1, total: 1 } })
    svc.userService.resetPassword.mockResolvedValue({ temporary_password: 'Temp#1234' })
    render(<MemoryRouter><StudentManagement /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button', { name: 'Reset password for Asha' }))
    const confirm = await screen.findByRole('dialog')
    expect(within(confirm).getByText(/Reset the password for Asha/)).toBeInTheDocument()
    await userEvent.click(within(confirm).getByRole('button', { name: 'Reset password' }))
    expect(svc.userService.resetPassword).toHaveBeenCalledWith(41)
    expect(await screen.findByText('Temp#1234')).toBeInTheDocument()
  })
})
