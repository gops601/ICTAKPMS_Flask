import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { batchMentorService, batchService, projectService, psService, studentService } from '../../services/adminService'
import { errorMessage } from '../../services/api'
import useBasePath from '../../hooks/useBasePath'
import PageHeader from '../../components/PageHeader'
import Alert from '../../components/Alert'
import Spinner from '../../components/Spinner'

/** Allocate one problem statement to selected students, individually or as a single team. */
export default function AllocatePage() {
  const { id } = useParams()
  const base = useBasePath()
  const navigate = useNavigate()
  const [batch, setBatch] = useState(null)
  const [students, setStudents] = useState([])
  const [statements, setStatements] = useState([])
  const [mentors, setMentors] = useState([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(new Set())
  const [form, setForm] = useState({ ps_id: '', mode: 'individual', mentor_id: '', start_date: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    (async () => {
      try {
        const b = await batchService.get(id)
        setBatch(b)
        const [s, ps, m] = await Promise.all([
          studentService.list({ batch_id: id, per_page: 100 }),
          psService.list({ domain_id: b.domain?.id, status: 'active', per_page: 100 }),
          batchMentorService.list(id),
        ])
        setStudents(s.items); setStatements(ps.items); setMentors(m)
      } catch (e) { setError(errorMessage(e)) } finally { setLoading(false) }
    })()
  }, [id])

  const free = students.filter((s) => !s.project)
  const toggle = (sid) => setSelected((cur) => { const n = new Set(cur); n.has(sid) ? n.delete(sid) : n.add(sid); return n })
  const allSelected = free.length > 0 && selected.size === free.length

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    if (!form.ps_id) return setError('Choose a project from the Project Shelf.')
    if (selected.size === 0) return setError('Select at least one student.')
    setBusy(true)
    try {
      await projectService.allocate({
        batch_id: Number(id), mentor_id: form.mentor_id ? Number(form.mentor_id) : null, start_date: form.start_date || null,
        items: [{ problem_statement_id: Number(form.ps_id), student_ids: [...selected], team: form.mode === 'team' }],
      })
      navigate(`${base}/batches/${id}`)
    } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }

  if (loading) return <Spinner />
  if (!batch) return <Alert>{error}</Alert>

  return (
    <div className="max-w-4xl space-y-4">
      <PageHeader title={`Allocate projects – ${batch.code}`} subtitle="Pick a project from the Project Shelf, then the students who will work on it." />
      <form onSubmit={submit} className="space-y-4">
        <Alert>{error}</Alert>
        <div className="card grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="al-ps" className="label">Project (from the Project Shelf) *</label>
            <select id="al-ps" className="input" value={form.ps_id} onChange={(e) => setForm({ ...form, ps_id: e.target.value })}>
              <option value="">Select…</option>{statements.map((p) => <option key={p.id} value={p.id}>{p.ps_code} – {p.title} ({p.difficulty})</option>)}
            </select>
            {statements.length === 0 && <p className="mt-1 text-xs text-orange-700">No active projects on the Project Shelf for this domain yet.</p>}
          </div>
          <div>
            <label htmlFor="al-mentor" className="label">Mentor (optional override)</label>
            <select id="al-mentor" className="input" value={form.mentor_id} onChange={(e) => setForm({ ...form, mentor_id: e.target.value })}>
              <option value="">Use the batch's mentors</option>{mentors.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="al-start" className="label">Start date (defaults to the batch's project start date, else today)</label>
            <input id="al-start" type="date" className="input" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} />
          </div>
          <fieldset>
            <legend className="label">Allocation mode</legend>
            <label className="mr-4 text-sm"><input type="radio" name="mode" checked={form.mode === 'individual'} onChange={() => setForm({ ...form, mode: 'individual' })} /> Individual projects (one each)</label>
            <label className="text-sm"><input type="radio" name="mode" checked={form.mode === 'team'} onChange={() => setForm({ ...form, mode: 'team' })} /> One team project</label>
          </fieldset>
        </div>

        <div className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold">Students ({selected.size} selected)</h2>
            <label className="text-sm"><input type="checkbox" checked={allSelected} onChange={() => setSelected(allSelected ? new Set() : new Set(free.map((s) => s.id)))} /> Select all available</label>
          </div>
          <ul className="divide-y divide-slate-100">
            {students.length === 0 && <li className="py-6 text-center text-sm text-slate-500">This batch has no students.</li>}
            {students.map((s) => (
              <li key={s.id} className="flex items-center gap-3 py-2 text-sm">
                <input type="checkbox" aria-label={`Select ${s.name}`} disabled={Boolean(s.project)} checked={selected.has(s.id)} onChange={() => toggle(s.id)} />
                <span className="font-medium">{s.name}</span><span className="text-slate-500">{s.registration_no}</span>
                {s.project && <span className="ml-auto text-xs text-slate-500">Already allocated: {s.project.title}</span>}
              </li>
            ))}
          </ul>
        </div>
        <div className="flex justify-end gap-2">
          <Link to={`${base}/batches/${id}`} className="btn-secondary">Cancel</Link>
          <button className="btn-primary" disabled={busy}>{busy ? 'Allocating…' : 'Allocate'}</button>
        </div>
      </form>
    </div>
  )
}
