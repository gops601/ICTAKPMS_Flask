import { useCallback, useEffect, useState } from 'react'
import { Layers, Pencil, Plus, Users } from 'lucide-react'
import { domainService, userService } from '../../services/adminService'
import { errorMessage, fieldErrors } from '../../services/api'
import PageHeader from '../../components/PageHeader'
import DataTable from '../../components/DataTable'
import Modal from '../../components/Modal'
import ConfirmDialog from '../../components/ConfirmDialog'
import StatusBadge from '../../components/StatusBadge'
import Alert from '../../components/Alert'

function DomainFormModal({ domain, onClose, onSaved }) {
  const [form, setForm] = useState({ name: domain?.name || '', code: domain?.code || '', description: domain?.description || '' })
  const [error, setError] = useState('')
  const [errs, setErrs] = useState({})
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError(''); setErrs({})
    try {
      if (domain) await domainService.update(domain.id, { name: form.name, description: form.description })
      else await domainService.create(form)
      onSaved()
    } catch (err) { setError(errorMessage(err)); setErrs(fieldErrors(err)) } finally { setBusy(false) }
  }

  return (
    <Modal title={domain ? 'Edit domain' : 'Add domain'} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <Alert>{error}</Alert>
        <div>
          <label htmlFor="d-name" className="label">Name</label>
          <input id="d-name" className="input" required value={form.name} onChange={set('name')} />
          {errs.name && <p className="mt-1 text-xs text-red-600">{errs.name}</p>}
        </div>
        <div>
          <label htmlFor="d-code" className="label">Code</label>
          <input id="d-code" className="input" required disabled={Boolean(domain)} value={form.code} onChange={set('code')} />
          {errs.code && <p className="mt-1 text-xs text-red-600">{errs.code}</p>}
        </div>
        <div>
          <label htmlFor="d-desc" className="label">Description</label>
          <textarea id="d-desc" className="input" rows={3} value={form.description} onChange={set('description')} />
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
        </div>
      </form>
    </Modal>
  )
}

function LeadsModal({ domain, onClose, onSaved }) {
  const [leads, setLeads] = useState([])
  const [selected, setSelected] = useState(new Set(domain.leads.map((l) => l.id)))
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    userService.list({ role: 'domain_lead', active: 1, per_page: 100 }).then((r) => setLeads(r.items)).catch((e) => setError(errorMessage(e)))
  }, [])

  const toggle = (id) => {
    const next = new Set(selected)
    next.has(id) ? next.delete(id) : next.add(id)
    setSelected(next)
  }
  const save = async () => {
    setBusy(true); setError('')
    try { await domainService.setLeads(domain.id, [...selected]); onSaved() } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }

  return (
    <Modal title={`Domain leads – ${domain.name}`} onClose={onClose}
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" onClick={save} disabled={busy}>{busy ? 'Saving…' : 'Save'}</button></>}>
      <Alert>{error}</Alert>
      {leads.length === 0 && !error && <p className="text-sm text-slate-500">No domain lead accounts exist yet. Create them under Users first.</p>}
      <ul className="space-y-2">
        {leads.map((u) => (
          <li key={u.id}>
            <label className="flex items-center gap-3 text-sm">
              <input type="checkbox" checked={selected.has(u.id)} onChange={() => toggle(u.id)} />
              <span className="font-medium">{u.name}</span><span className="text-slate-500">{u.email}</span>
            </label>
          </li>
        ))}
      </ul>
    </Modal>
  )
}

/** Add, rename and (de)activate the subdomains of one domain. Project Shelf entries pick from these. */
export function SubdomainsModal({ domain, onClose, onChanged }) {
  const [subs, setSubs] = useState(domain.subdomains || [])
  const [name, setName] = useState('')
  const [editing, setEditing] = useState(null) // { id, name }
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const run = async (fn) => {
    setBusy(true); setError('')
    try { await fn(); onChanged() } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  const add = (e) => {
    e.preventDefault()
    run(async () => { const sd = await domainService.addSubdomain(domain.id, name); setSubs((s) => [...s, sd].sort((a, b) => a.name.localeCompare(b.name))); setName('') })
  }
  const rename = () => run(async () => {
    const sd = await domainService.updateSubdomain(editing.id, { name: editing.name })
    setSubs((s) => s.map((x) => (x.id === sd.id ? sd : x))); setEditing(null)
  })
  const toggleActive = (sd) => run(async () => {
    const upd = await domainService.updateSubdomain(sd.id, { is_active: !sd.is_active })
    setSubs((s) => s.map((x) => (x.id === upd.id ? upd : x)))
  })

  return (
    <Modal title={`Subdomains – ${domain.name}`} onClose={onClose} footer={<button className="btn-primary" onClick={onClose}>Done</button>}>
      <div className="space-y-3">
        <Alert>{error}</Alert>
        <form onSubmit={add} className="flex gap-2">
          <input className="input" required minLength={2} placeholder="e.g. Computer Vision" aria-label="New subdomain name" value={name} onChange={(e) => setName(e.target.value)} />
          <button className="btn-primary shrink-0" disabled={busy}><Plus className="h-4 w-4" />Add</button>
        </form>
        {subs.length === 0 && <p className="text-sm text-slate-500">No subdomains yet. Once you add one, every project on the shelf for this domain must choose a subdomain.</p>}
        <ul className="divide-y divide-slate-100">
          {subs.map((sd) => (
            <li key={sd.id} className="flex items-center justify-between gap-2 py-2 text-sm">
              {editing?.id === sd.id ? (
                <>
                  <input className="input" aria-label={`Rename ${sd.name}`} value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
                  <div className="flex gap-2"><button className="btn-primary" disabled={busy} onClick={rename}>Save</button><button className="btn-secondary" onClick={() => setEditing(null)}>Cancel</button></div>
                </>
              ) : (
                <>
                  <span className={sd.is_active ? 'font-medium' : 'text-slate-400 line-through'}>{sd.name}</span>
                  <div className="flex gap-2">
                    <button className="btn-secondary" onClick={() => setEditing({ id: sd.id, name: sd.name })}><Pencil className="h-4 w-4" />Rename</button>
                    <button className="btn-secondary" disabled={busy} onClick={() => toggleActive(sd)}>{sd.is_active ? 'Deactivate' : 'Activate'}</button>
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      </div>
    </Modal>
  )
}

export default function DomainManagement() {
  const [domains, setDomains] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(null)
  const [leadsFor, setLeadsFor] = useState(null)
  const [subsFor, setSubsFor] = useState(null)
  const [toggle, setToggle] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try { setDomains(await domainService.list()) } catch (e) { setError(errorMessage(e)) } finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])

  const confirmToggle = async () => {
    setBusy(true)
    try { await domainService.setActive(toggle.id, !toggle.is_active); setToggle(null); load() }
    catch (e) { setError(errorMessage(e)); setToggle(null) } finally { setBusy(false) }
  }

  return (
    <div>
      <PageHeader title="Domains" subtitle="Project domains, their leads and batch statistics."
        actions={<button className="btn-primary" onClick={() => setEditing('new')}><Plus className="h-4 w-4" />Add domain</button>} />
      <Alert>{error}</Alert>
      <div className="card mt-3">
        <DataTable loading={loading} rows={domains} columns={[
          { key: 'name', header: 'Domain' },
          { key: 'code', header: 'Code' },
          { key: 'leads', header: 'Domain leads', render: (d) => d.leads.length ? d.leads.map((l) => l.name).join(', ') : <span className="text-slate-400">Unassigned</span> },
          { key: 'subdomains', header: 'Subdomains', render: (d) => (d.subdomains || []).filter((s) => s.is_active).length ? (d.subdomains).filter((s) => s.is_active).map((s) => s.name).join(', ') : <span className="text-slate-400">None</span> },
          { key: 'batch_count', header: 'Batches' },
          { key: 'student_count', header: 'Students' },
          { key: 'status', header: 'Status', render: (d) => <StatusBadge status={d.is_active ? 'active' : 'inactive'} /> },
          { key: 'actions', header: 'Actions', render: (d) => (
            <div className="flex flex-wrap gap-2">
              <button className="btn-secondary" onClick={() => setEditing(d)}><Pencil className="h-4 w-4" />Edit</button>
              <button className="btn-secondary" onClick={() => setLeadsFor(d)}><Users className="h-4 w-4" />Leads</button>
              <button className="btn-secondary" onClick={() => setSubsFor(d)}><Layers className="h-4 w-4" />Subdomains</button>
              <button className="btn-secondary" onClick={() => setToggle(d)}>{d.is_active ? 'Deactivate' : 'Activate'}</button>
            </div>
          ) },
        ]} />
      </div>
      {editing && <DomainFormModal domain={editing === 'new' ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load() }} />}
      {subsFor && <SubdomainsModal domain={subsFor} onClose={() => { setSubsFor(null) }} onChanged={load} />}
      {leadsFor && <LeadsModal domain={leadsFor} onClose={() => setLeadsFor(null)} onSaved={() => { setLeadsFor(null); load() }} />}
      {toggle && (
        <ConfirmDialog message={toggle.is_active ? `Deactivate ${toggle.name}? New batches cannot be assigned to it.` : `Activate ${toggle.name}?`}
          confirmLabel={toggle.is_active ? 'Deactivate' : 'Activate'} danger={toggle.is_active} busy={busy}
          onConfirm={confirmToggle} onCancel={() => setToggle(null)} />
      )}
    </div>
  )
}
