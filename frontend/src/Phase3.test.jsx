import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProblemStatementForm from './pages/domain_lead/ProblemStatementForm'
import ProblemStatementDetail from './pages/domain_lead/ProblemStatementDetail'
import ProblemStatementList from './pages/domain_lead/ProblemStatementList'
import AttachmentPanel from './components/AttachmentPanel'
import ImportWizard from './components/ImportWizard'
import App from './App'
import { AuthProvider } from './context/AuthContext'
import api from './services/api'
import * as admin from './services/adminService'

vi.mock('./hooks/useBasePath', () => ({ default: () => '/lead' }))
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
vi.mock('./services/adminService', async () => {
  const actual = await vi.importActual('./services/adminService')
  return {
    ...actual,
    downloadFile: vi.fn(),
    ouService: { list: vi.fn().mockResolvedValue([]) },
    domainService: { list: vi.fn() },
    psService: { list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), setStatus: vi.fn(), upload: vi.fn(), removeFile: vi.fn(), download: vi.fn(), industries: vi.fn().mockResolvedValue([]) },
    importService: { upload: vi.fn(), confirm: vi.fn() },
  }
})

const DOMAINS = [{ id: 5, name: 'AI & ML' }]
const PS = {
  id: 3, ps_code: 'PS-3', title: 'Smart Attendance', difficulty: 'hard', status: 'active', estimated_duration: '4 weeks',
  domain: { id: 5, name: 'AI & ML' }, description: '<p>Build <b>it</b></p>', objectives: '<ul><li>Goal</li></ul>', can_edit: true,
  datasets: [{ id: 1, name: 'train.csv', size_bytes: 2048, description: 'training' }],
  documents: [],
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  admin.domainService.list.mockResolvedValue(DOMAINS)
  admin.psService.get.mockResolvedValue(PS)
})

const inRoutes = (path, el, routePath) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={routePath} element={el} />
        <Route path="/lead/problem-statements/:id/edit" element={<div>Edit page</div>} />
      </Routes>
    </MemoryRouter>,
  )

describe('problem statement form', () => {
  const fillBasics = async () => {
    await userEvent.type(await screen.findByLabelText(/problem statement id/i), 'PS-9')
    await userEvent.type(screen.getByLabelText(/project title/i), 'Chatbot')
    await userEvent.selectOptions(screen.getByLabelText(/^domain/i), '5')
  }

  it('submits rich text from the editor and moves to the edit page for attachments', async () => {
    admin.psService.create.mockResolvedValue({ id: 9 })
    inRoutes('/lead/problem-statements/new', <ProblemStatementForm />, '/lead/problem-statements/new')
    await fillBasics()
    const editor = screen.getByRole('textbox', { name: 'Project description' })
    editor.innerHTML = '<p>Hello <b>world</b></p>'
    fireEvent.input(editor)
    await userEvent.click(screen.getByRole('button', { name: /create & add files/i }))
    await waitFor(() => expect(admin.psService.create).toHaveBeenCalled())
    expect(admin.psService.create.mock.calls[0][0]).toMatchObject({
      ps_code: 'PS-9', title: 'Chatbot', domain_id: 5, difficulty: 'medium', description: '<p>Hello <b>world</b></p>',
    })
    expect(await screen.findByText('Edit page')).toBeInTheDocument()
  })

  it('shows server validation errors per field', async () => {
    admin.psService.create.mockRejectedValue({
      response: { status: 422, data: { message: 'Validation failed', errors: { ps_code: "Problem statement ID 'PS-9' already exists", description: 'Provide a project description or a problem definition' } } },
    })
    inRoutes('/lead/problem-statements/new', <ProblemStatementForm />, '/lead/problem-statements/new')
    await fillBasics()
    await userEvent.click(screen.getByRole('button', { name: /create & add files/i }))
    expect((await screen.findAllByText(/already exists/)).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/provide a project description/i).length).toBeGreaterThan(0)
    expect(screen.getByRole('alert')).toHaveTextContent('Validation failed')
  })

  it('loads an existing record, locks the ID and shows attachment panels', async () => {
    inRoutes('/lead/problem-statements/3/edit', <ProblemStatementForm />, '/lead/problem-statements/:id/edit')
    expect(await screen.findByDisplayValue('Smart Attendance')).toBeInTheDocument()
    expect(screen.getByLabelText(/problem statement id/i)).toBeDisabled()
    expect(screen.getByRole('textbox', { name: 'Project description' }).innerHTML).toContain('<b>it</b>')
    expect(screen.getByText('train.csv')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Reference documents' })).toBeInTheDocument()
  })
})

describe('attachments (file upload)', () => {
  const file = new File(['a,b\n1,2'], 'data.csv', { type: 'text/csv' })

  it('uploads a file with its description then refreshes', async () => {
    admin.psService.upload.mockResolvedValue({})
    const onChanged = vi.fn()
    render(<AttachmentPanel psId={3} kind="datasets" title="Datasets" canEdit items={[]} onChanged={onChanged} />)
    await userEvent.upload(screen.getByLabelText(/choose datasets file/i), file)
    await userEvent.type(screen.getByLabelText(/datasets description/i), 'raw data')
    await userEvent.click(screen.getByRole('button', { name: /^upload$/i }))
    await waitFor(() => expect(admin.psService.upload).toHaveBeenCalledWith(3, 'datasets', file, 'raw data'))
    expect(onChanged).toHaveBeenCalled()
  })

  it('shows the server message when a file is rejected', async () => {
    admin.psService.upload.mockRejectedValue({ response: { status: 422, data: { message: 'File type .exe is not allowed' } } })
    render(<AttachmentPanel psId={3} kind="datasets" title="Datasets" canEdit items={[]} onChanged={vi.fn()} />)
    await userEvent.upload(screen.getByLabelText(/choose datasets file/i), file)
    await userEvent.click(screen.getByRole('button', { name: /^upload$/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('.exe is not allowed')
  })

  it('requires a file before uploading', async () => {
    render(<AttachmentPanel psId={3} kind="datasets" title="Datasets" canEdit items={[]} onChanged={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /^upload$/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/choose a file/i)
    expect(admin.psService.upload).not.toHaveBeenCalled()
  })

  it('confirms before deleting and supports download', async () => {
    admin.psService.removeFile.mockResolvedValue({})
    const items = PS.datasets
    const onChanged = vi.fn()
    render(<AttachmentPanel psId={3} kind="datasets" title="Datasets" canEdit items={items} onChanged={onChanged} />)
    await userEvent.click(screen.getByRole('button', { name: /download train.csv/i }))
    expect(admin.psService.download).toHaveBeenCalledWith(3, 'datasets', items[0])
    await userEvent.click(screen.getByRole('button', { name: /delete train.csv/i }))
    expect(admin.psService.removeFile).not.toHaveBeenCalled()
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /delete file/i }))
    await waitFor(() => expect(admin.psService.removeFile).toHaveBeenCalledWith(3, 'datasets', 1))
  })

  it('is read-only without edit permission (no upload or delete controls)', () => {
    render(<AttachmentPanel psId={3} kind="datasets" title="Datasets" canEdit={false} items={PS.datasets} onChanged={vi.fn()} />)
    expect(screen.getByRole('button', { name: /download train.csv/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^upload$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument()
  })
})

describe('problem statement detail & list', () => {
  it('renders sanitised sections and the edit link only when permitted', async () => {
    inRoutes('/lead/problem-statements/3', <ProblemStatementDetail />, '/lead/problem-statements/:id')
    expect(await screen.findByRole('heading', { name: 'Smart Attendance' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Project objectives' })).toHaveTextContent('Goal')
    expect(screen.queryByRole('region', { name: 'Scope' })).not.toBeInTheDocument() // empty sections hidden
    expect(screen.getByRole('link', { name: /edit/i })).toBeInTheDocument()
  })

  it('hides Edit for read-only viewers', async () => {
    admin.psService.get.mockResolvedValue({ ...PS, can_edit: false })
    inRoutes('/lead/problem-statements/3', <ProblemStatementDetail />, '/lead/problem-statements/:id')
    await screen.findByRole('heading', { name: 'Smart Attendance' })
    expect(screen.queryByRole('link', { name: /edit/i })).not.toBeInTheDocument()
  })

  it('lists statements and toggles status after confirmation', async () => {
    admin.psService.list.mockResolvedValue({ items: [{ ...PS, dataset_count: 1, document_count: 0 }], meta: { page: 1, pages: 1, total: 1 } })
    admin.psService.setStatus.mockResolvedValue({})
    inRoutes('/lead/problem-statements', <ProblemStatementList />, '/lead/problem-statements')
    expect(await screen.findByText('Smart Attendance')).toBeInTheDocument()
    expect(screen.getByText('1 datasets · 0 docs')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /^deactivate$/i }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /deactivate/i }))
    await waitFor(() => expect(admin.psService.setStatus).toHaveBeenCalledWith(3, 'inactive'))
  })
})

describe('problem statement bulk upload wizard', () => {
  it('has no OU selector, keeps template buttons enabled and uploads without an OU', async () => {
    const file = new File(['x'], 'ps.csv', { type: 'text/csv' })
    admin.importService.upload.mockResolvedValue({ id: 1, total_rows: 1, valid_rows: 1, error_rows: 0, preview: [{ row_number: 2, status: 'valid', data: { a: 'b' }, errors: [] }] })
    render(<ImportWizard type="problem_statements" title="PS upload" />)
    expect(screen.queryByLabelText(/select ou/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /excel/i })).toBeEnabled()
    await userEvent.click(screen.getByRole('button', { name: /^csv$/i }))
    expect(admin.downloadFile).toHaveBeenCalledWith('/problem-statements/template', { format: 'csv' }, 'problem_statements_template.csv')
    await userEvent.upload(screen.getByLabelText(/upload completed file/i), file)
    await userEvent.click(screen.getByRole('button', { name: /upload & validate/i }))
    await waitFor(() => expect(admin.importService.upload).toHaveBeenCalledWith('problem_statements', null, file))
    expect(await screen.findByRole('button', { name: /confirm import/i })).toBeEnabled()
  })
})

describe('navigation', () => {
  it('shows problem statement links for domain leads and admins only', async () => {
    localStorage.setItem('plms_access', 'tok')
    api.get.mockResolvedValueOnce({ data: { data: { id: 1, name: 'Lea', email: 'l@x.com', role: 'domain_lead', must_change_password: false } } })
    render(<MemoryRouter initialEntries={['/lead']}><AuthProvider><App /></AuthProvider></MemoryRouter>)
    const nav = await screen.findByRole('navigation', { name: /main navigation/i })
    expect(nav).toHaveTextContent('Problem Statements')
    expect(nav).toHaveTextContent('Bulk Upload')
  })

  it('keeps students out of problem statement management routes', async () => {
    localStorage.setItem('plms_access', 'tok')
    api.get.mockResolvedValueOnce({ data: { data: { id: 2, name: 'Stu', email: 's@x.com', role: 'student', must_change_password: false } } })
    render(<MemoryRouter initialEntries={['/lead/problem-statements']}><AuthProvider><App /></AuthProvider></MemoryRouter>)
    expect(await screen.findByText(/welcome, stu/i)).toBeInTheDocument()
  })
})
