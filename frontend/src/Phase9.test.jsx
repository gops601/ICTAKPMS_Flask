import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StudentManagement from './pages/admin/StudentManagement'
import ProjectList from './pages/common/ProjectList'
import { ScrumOverviewPage } from './pages/common/ScrumPages'
import { SrsQueuePage } from './pages/common/SrsPages'
import { EvaluationQueuePage } from './pages/common/ReviewPages'
import AuthLayout from './layouts/AuthLayout'
import { credentialsCsv, rowFromStudent } from './utils/credentials'
import { APP_NAME } from './utils/brand'
import * as svc from './services/adminService'

let mockUser = { id: 1, name: 'Ada', role: 'admin' }
vi.mock('./context/AuthContext', async () => {
  const actual = await vi.importActual('./context/AuthContext')
  return { ...actual, useAuth: () => ({ user: mockUser }) }
})
vi.mock('./services/adminService', async () => {
  const actual = await vi.importActual('./services/adminService')
  return {
    ...actual,
    downloadTextFile: vi.fn(),
    batchService: { list: vi.fn() },
    studentService: { list: vi.fn(), create: vi.fn(), credentials: vi.fn() },
    projectService: { list: vi.fn() },
    scrumService: { overview: vi.fn() },
    srsService: { queue: vi.fn() },
    reviewService: { queue: vi.fn() },
  }
})

const BATCHES = [{ id: 5, code: 'C1', name: 'Credential batch' }, { id: 6, code: 'C2', name: 'Other batch' }]
const EMPTY = { items: [], meta: { page: 1, pages: 1, total: 0 } }

beforeEach(() => {
  vi.clearAllMocks()
  mockUser = { id: 1, name: 'Ada', role: 'admin' }
  svc.batchService.list.mockResolvedValue({ items: BATCHES, meta: {} })
  svc.studentService.list.mockResolvedValue(EMPTY)
})

const ROW = { name: 'Asha K', email: 'asha@x.com', phone: '9999999999', registration_no: 'R1', batch_code: 'C1', batch_name: 'Credential batch', temporary_password: 'Tmp12345ab' }

describe('credentials file', () => {
  it('has every detail a student needs to log in, opens cleanly in Excel and uses CRLF rows', () => {
    const csv = credentialsCsv([ROW], 'https://lms.example.org')
    const [header, row] = csv.replace('﻿', '').trim().split('\r\n')
    expect(csv.startsWith('﻿')).toBe(true)
    expect(header).toBe('"Name","Login ID (email)","Temporary password","Registration number","Phone","Batch code","Batch name","Login URL"')
    expect(row).toBe('"Asha K","asha@x.com","Tmp12345ab","R1","9999999999","C1","Credential batch","https://lms.example.org"')
  })

  it('escapes quotes and neutralises spreadsheet formulas coming from uploaded names', () => {
    const csv = credentialsCsv([{ ...ROW, name: '=HYPERLINK("http://evil","x")', batch_name: 'He said "hi"' }], 'https://x')
    expect(csv).toContain(`"'=HYPERLINK(""http://evil"",""x"")"`)
    expect(csv).toContain('"He said ""hi"""')
    expect(csv).not.toMatch(/,"=/)
  })

  it('builds a row from a newly created student', () => {
    expect(rowFromStudent({ name: 'Ben', email: 'b@x.com', phone: null, registration_no: 'R2', batch: { code: 'C1', name: 'Credential batch' }, temporary_password: 'pw' }))
      .toEqual({ name: 'Ben', email: 'b@x.com', phone: '', registration_no: 'R2', batch_code: 'C1', batch_name: 'Credential batch', temporary_password: 'pw' })
  })
})

describe('students page – download credentials', () => {
  const renderPage = () => render(<MemoryRouter><StudentManagement /></MemoryRouter>)
  const open = async () => {
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: /download credentials/i }))
    return screen.getByRole('dialog')
  }

  it('explains what will happen, requires a batch, then offers the shareable file', async () => {
    svc.studentService.credentials.mockResolvedValue({
      credentials: [ROW, { ...ROW, name: 'Ben J', email: 'ben@x.com', registration_no: 'R2', temporary_password: 'Zz99999999' }],
      skipped: [{ name: 'Cara L', registration_no: 'R3', reason: 'Already set their own password' }], batch: { code: 'C1', name: 'Credential batch' },
    })
    const dialog = await open()
    expect(within(dialog).getByText(/new temporary password/i)).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: /generate passwords/i })).toBeDisabled()
    await waitFor(() => expect(within(dialog).getByRole('option', { name: 'C1 – Credential batch' })).toBeInTheDocument())
    await userEvent.selectOptions(within(dialog).getByLabelText(/^batch$/i), '5')
    await userEvent.click(within(dialog).getByRole('button', { name: /generate passwords/i }))
    await waitFor(() => expect(svc.studentService.credentials).toHaveBeenCalledWith(5))
    expect(await within(dialog).findByText(/2 student\(s\) ready for batch C1\. 1 skipped\./)).toBeInTheDocument()
    expect(within(dialog).getByText(/cannot be shown again/i)).toBeInTheDocument()
    expect(within(dialog).getByLabelText('Skipped students')).toHaveTextContent('Cara L (R3) – Already set their own password')
    await userEvent.click(within(dialog).getByRole('button', { name: /download student details with passwords/i }))
    const [csv, filename] = svc.downloadTextFile.mock.calls[0]
    expect(filename).toBe('C1_student_credentials.csv')
    expect(csv).toContain('"asha@x.com","Tmp12345ab","R1"')
    expect(csv).toContain('"ben@x.com","Zz99999999","R2"')
  })

  it('does not offer a file when everybody was skipped', async () => {
    svc.studentService.credentials.mockResolvedValue({ credentials: [], skipped: [{ name: 'Cara L', registration_no: 'R3', reason: 'Already set their own password' }], batch: { code: 'C1', name: 'x' } })
    const dialog = await open()
    await waitFor(() => expect(within(dialog).getByRole('option', { name: /C1/ })).toBeInTheDocument())
    await userEvent.selectOptions(within(dialog).getByLabelText(/^batch$/i), '5')
    await userEvent.click(within(dialog).getByRole('button', { name: /generate passwords/i }))
    expect(await within(dialog).findByText(/no new passwords were issued/i)).toBeInTheDocument()
    expect(within(dialog).queryByRole('button', { name: /download student details/i })).not.toBeInTheDocument()
  })

  it('shows the server error and lets the admin retry', async () => {
    svc.studentService.credentials.mockRejectedValue({ response: { status: 422, data: { message: 'Batch not found' } } })
    const dialog = await open()
    await waitFor(() => expect(within(dialog).getByRole('option', { name: /C1/ })).toBeInTheDocument())
    await userEvent.selectOptions(within(dialog).getByLabelText(/^batch$/i), '5')
    await userEvent.click(within(dialog).getByRole('button', { name: /generate passwords/i }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Batch not found')
    expect(within(dialog).getByRole('button', { name: /generate passwords/i })).toBeEnabled()
  })

  it('offers the login details file right after adding a single student', async () => {
    svc.studentService.create.mockResolvedValue({ name: 'Dev P', email: 'dev@x.com', phone: '9000000000', registration_no: 'R9', batch: { code: 'C1', name: 'Credential batch' }, temporary_password: 'Once12345' })
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: /^add student$/i }))
    const dialog = screen.getByRole('dialog')
    await waitFor(() => expect(within(dialog).getByRole('option', { name: /C1/ })).toBeInTheDocument())
    await userEvent.selectOptions(within(dialog).getByLabelText(/batch \*/i), '5')
    await userEvent.type(within(dialog).getByLabelText(/^name/i), 'Dev P')
    await userEvent.type(within(dialog).getByLabelText(/^email/i), 'dev@x.com')
    await userEvent.type(within(dialog).getByLabelText(/registration number/i), 'R9')
    await userEvent.click(within(dialog).getByRole('button', { name: /create student/i }))
    expect(await screen.findByText('Once12345')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /download login details/i }))
    const [csv, filename] = svc.downloadTextFile.mock.calls[0]
    expect(filename).toBe('R9_login_details.csv')
    expect(csv).toContain('"dev@x.com","Once12345","R9","9000000000","C1"')
  })
})

describe('batch filter on list pages', () => {
  const choose = async (label = 'Filter by batch') => {
    const select = await screen.findByLabelText(label)
    await waitFor(() => expect(within(select).getAllByRole('option').length).toBe(3))
    await userEvent.selectOptions(select, '6')
  }

  it('projects', async () => {
    svc.projectService.list.mockResolvedValue(EMPTY)
    render(<MemoryRouter><ProjectList /></MemoryRouter>)
    await choose()
    await waitFor(() => expect(svc.projectService.list).toHaveBeenLastCalledWith(expect.objectContaining({ batch_id: '6', page: 1 })))
  })

  it('scrum monitoring', async () => {
    svc.scrumService.overview.mockResolvedValue(EMPTY)
    render(<MemoryRouter><ScrumOverviewPage /></MemoryRouter>)
    await choose()
    await waitFor(() => expect(svc.scrumService.overview).toHaveBeenLastCalledWith({ page: 1, batch_id: '6', overdue: undefined }))
  })

  it('SRS queue', async () => {
    mockUser = { id: 4, name: 'Mia', role: 'mentor' }
    svc.srsService.queue.mockResolvedValue(EMPTY)
    render(<MemoryRouter><SrsQueuePage /></MemoryRouter>)
    await choose()
    await waitFor(() => expect(svc.srsService.queue).toHaveBeenLastCalledWith({ page: 1, batch_id: '6' }))
  })

  it('weekly evaluations, combined with the other filters, and resets to page 1', async () => {
    mockUser = { id: 4, name: 'Mia', role: 'mentor' }
    svc.reviewService.queue.mockResolvedValue({ items: [], meta: { page: 2, pages: 3, total: 50 } })
    render(<MemoryRouter><EvaluationQueuePage /></MemoryRouter>)
    await choose()
    await userEvent.selectOptions(screen.getByLabelText('Filter by week'), '2')
    await waitFor(() => expect(svc.reviewService.queue).toHaveBeenLastCalledWith({ page: 1, batch_id: '6', week: '2', overdue: undefined }))
    await userEvent.selectOptions(screen.getByLabelText('Filter by batch'), '')
    await waitFor(() => expect(svc.reviewService.queue).toHaveBeenLastCalledWith({ page: 1, batch_id: undefined, week: '2', overdue: undefined }))
  })
})

describe('app name', () => {
  it('is ICTAK on the sign-in screen', () => {
    expect(APP_NAME).toBe('ICTAK')
    render(<AuthLayout title="Sign in"><p>form</p></AuthLayout>)
    expect(screen.getAllByText('ICTAK').length).toBeGreaterThan(0)
    expect(screen.queryByText(/PLMS|ProjectLMS/)).not.toBeInTheDocument()
  })
})
