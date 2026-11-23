import { useEffect, useState } from 'react'
import { KeyRound, Plus } from 'lucide-react'
import { domainService, userService } from '../../services/adminService'
import { errorMessage, fieldErrors } from '../../services/api'
import { useDebounced, useList } from '../../hooks/useList'
import { ROLE_LABEL } from '../../utils/roles'
import PageHeader from '../../components/PageHeader'
import DataTable from '../../components/DataTable'
import Pagination from '../../components/Pagination'
import Modal from '../../components/Modal'
import ConfirmDialog from '../../components/ConfirmDialog'
import StatusBadge from '../../components/StatusBadge'
import Alert from '../../components/Alert'

function CreateUserModal({ domains, onClose, onDone, fixedRole }) {
  const [form, setForm] = useState({ role: fixedRole || 'mentor', name: '', email: '', phone: '', domain_id: '', designation: '' })
  const [error, setError] = useState('')
  const [errs, setErrs] = useState({})
  const [busy, setBusy] = useState(false)
  const [created, setCreated] = useState(null)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setError(''); setErrs({})
    const body = { role: form.role, name: form.name, email: form.email, phone: form.phone || null }
    if (form.role === 'mentor') {
      body.domain_id = form.domain_id ? Number(form.domain_id) : null
      body.designation = form.designation || null
    }
    try { setCreated(await userService.create(body)) } catch (err) { setError(errorMessage(err)); setErrs(fieldErrors(err)) } finally { setBusy(false) }
  }

  if (created) {
    return (
      <Modal title="User created" onClose={onDone}>
        <Alert type="warning">Temporary password for {created.email} (shown once): <b className="font-mono">{created.temporary_password}</b></Alert>
        <p className="mt-3 text-sm text-slate-600">The user must change it at first login.</p>
        <div className="mt-4 flex justify-end"><button className="btn-primary" onClick={onDone}>Done</button></div>
      </Modal>
    )
  }
  const err = (k) => errs[k] && <p className="mt-1 text-xs text-red-600">{errs[k]}</p>
  return (
    <Modal title="Create user" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <Alert>{error}</Alert>
        {!fixedRole && (
          <div><label htmlFor="u-role" className="label">Role</label>
            <select id="u-role" className="input" value={form.role} onChange={set('role')}>
              <option value="mentor">Mentor</option><option value="domain_lead">Domain Lead</option><option value="admin">Administrator</option>
            </select></div>
        )}
        <div><label htmlFor="u-name" className="label">Name *</label><input id="u-name" className="input" required value={form.name} onChange={set('name')} />{err('name')}</div>
        <div><label htmlFor="u-email" className="label">Email *</label><input id="u-email" type="email" className="input" required value={form.email} onChange={set('email')} />{err('email')}</div>
        <div><label htmlFor="u-phone" className="label">Phone</label><input id="u-phone" className="input" value={form.phone} onChange={set('phone')} /></div>
        {form.role === 'mentor' && (
          <>
            <div><label htmlFor="u-dom" className="label">Primary domain</label>
              <select id="u-dom" className="input" value={form.domain_id} onChange={set('domain_id')}>
                <option value="">None</option>{domains.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select></div>
            <div><label htmlFor="u-des" className="label">Designation</label><input id="u-des" className="input" value={form.designation} onChange={set('designation')} /></div>
          </>
        )}
        <p className="text-xs text-slate-500">A temporary password is generated automatically.</p>
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={busy}>{busy ? 'Creating…' : 'Create user'}</button>
        </div>
      </form>
    </Modal>
  )
}

export default function UserManagement({ fixedRole, title = 'Users', subtitle = 'Administrators, domain leads, mentors and students.', addLabel = 'Create user' }) {
  const [q, setQ] = useState('')
  const [role, setRole] = useState('')
  const [page, setPage] = useState(1)
  const [domains, setDomains] = useState([])
  const [creating, setCreating] = useState(false)
  const [resetFor, setResetFor] = useState(null)
  const [toggle, setToggle] = useState(null)
  const [tempPw, setTempPw] = useState(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const dq = useDebounced(q)

  useEffect(() => { domainService.list({ active: 1 }).then(setDomains).catch(() => {}) }, [])
  const { items, meta, loading, error, reload } = useList(userService.list, { q: dq, role: fixedRole || role || undefined, page })

  const doReset = async () => {
    setBusy(true)
    try { const r = await userService.resetPassword(resetFor.id); setTempPw({ user: resetFor, password: r.temporary_password }); setResetFor(null) }
    catch (e) { setActionError(errorMessage(e)); setResetFor(null) } finally { setBusy(false) }
  }
  const doToggle = async () => {
    setBusy(true)
    try { await userService.setActive(toggle.id, !toggle.is_active); setToggle(null); reload() }
    catch (e) { setActionError(errorMessage(e)); setToggle(null) } finally { setBusy(false) }
  }

  return (
    <div>
      <PageHeader title={title} subtitle={subtitle}
        actions={<button className="btn-primary" onClick={() => setCreating(true)}><Plus className="h-4 w-4" />{addLabel}</button>} />
      <div className="card">
        <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <input className="input" placeholder="Search name or email…" aria-label="Search users" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} />
          {!fixedRole && (
            <select className="input" aria-label="Filter by role" value={role} onChange={(e) => { setRole(e.target.value); setPage(1) }}>
              <option value="">All roles</option>
              {Object.entries(ROLE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          )}
        </div>
        <Alert>{error || actionError}</Alert>
        <DataTable loading={loading} rows={items} columns={[
          { key: 'name', header: 'Name' },
          { key: 'email', header: 'Email' },
          { key: 'role', header: 'Role', render: (u) => ROLE_LABEL[u.role] },
          { key: 'status', header: 'Status', render: (u) => <StatusBadge status={u.is_active ? 'active' : 'inactive'} /> },
          { key: 'actions', header: 'Actions', render: (u) => (
            <div className="flex gap-2">
              <button className="btn-secondary" onClick={() => setResetFor(u)}><KeyRound className="h-4 w-4" />Reset password</button>
              <button className="btn-secondary" onClick={() => setToggle(u)}>{u.is_active ? 'Deactivate' : 'Activate'}</button>
            </div>
          ) },
        ]} />
        <Pagination meta={meta} onPage={setPage} />
      </div>
      {creating && <CreateUserModal fixedRole={fixedRole} domains={domains} onClose={() => setCreating(false)} onDone={() => { setCreating(false); reload() }} />}
      {resetFor && <ConfirmDialog message={`Reset the password for ${resetFor.name}? A new temporary password will be generated.`} confirmLabel="Reset password" busy={busy} onConfirm={doReset} onCancel={() => setResetFor(null)} />}
      {toggle && <ConfirmDialog message={`${toggle.is_active ? 'Deactivate' : 'Activate'} ${toggle.name}?`} confirmLabel={toggle.is_active ? 'Deactivate' : 'Activate'} danger={toggle.is_active} busy={busy} onConfirm={doToggle} onCancel={() => setToggle(null)} />}
      {tempPw && (
        <Modal title="Password reset" onClose={() => setTempPw(null)}>
          <Alert type="warning">Temporary password for {tempPw.user.email} (shown once): <b className="font-mono">{tempPw.password}</b></Alert>
          <div className="mt-4 flex justify-end"><button className="btn-primary" onClick={() => setTempPw(null)}>Done</button></div>
        </Modal>
      )}
    </div>
  )
}
