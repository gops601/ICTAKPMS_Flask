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
  const [form, setForm] = useState({
    role: fixedRole || 'mentor', name: '', email: '', phone: '', domain_id: '', designation: '',
    mentor_type: 'internal', company: '', industry_sector: '', experience_years: '', linkedin_url: '', bio: '',
  })
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
      body.mentor_type = form.mentor_type
      if (form.mentor_type === 'industry') {
        Object.assign(body, {
          company: form.company, industry_sector: form.industry_sector, linkedin_url: form.linkedin_url || null, bio: form.bio,
          experience_years: form.experience_years === '' ? null : Number(form.experience_years),
        })
      }
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
  const industry = form.role === 'mentor' && form.mentor_type === 'industry'
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
            <fieldset>
              <legend className="label">Mentor type *</legend>
              <div className="flex gap-4 text-sm">
                <label className="flex items-center gap-2"><input type="radio" name="mentor_type" value="internal" checked={form.mentor_type === 'internal'} onChange={set('mentor_type')} />Internal (ICT trainer)</label>
                <label className="flex items-center gap-2"><input type="radio" name="mentor_type" value="industry" checked={form.mentor_type === 'industry'} onChange={set('mentor_type')} />External (industry mentor)</label>
              </div>
            </fieldset>
            <div><label htmlFor="u-des" className="label">Designation{industry && ' *'}</label><input id="u-des" className="input" required={industry} value={form.designation} onChange={set('designation')} />{err('designation')}</div>
            {industry && (
              <div className="space-y-3 rounded-lg bg-slate-50 p-3">
                <p className="text-xs font-medium text-slate-600">Industry mentor details</p>
                <div><label htmlFor="u-co" className="label">Company *</label><input id="u-co" className="input" required value={form.company} onChange={set('company')} />{err('company')}</div>
                <div><label htmlFor="u-sec" className="label">Industry / sector *</label><input id="u-sec" className="input" required placeholder="e.g. Healthcare, Finance" value={form.industry_sector} onChange={set('industry_sector')} />{err('industry_sector')}</div>
                <div><label htmlFor="u-exp" className="label">Years of experience</label><input id="u-exp" type="number" min="0" max="70" className="input" value={form.experience_years} onChange={set('experience_years')} />{err('experience_years')}</div>
                <div><label htmlFor="u-li" className="label">Profile link (LinkedIn / website)</label><input id="u-li" type="url" className="input" placeholder="https://…" value={form.linkedin_url} onChange={set('linkedin_url')} />{err('linkedin_url')}</div>
                <div><label htmlFor="u-bio" className="label">Professional profile *</label><textarea id="u-bio" className="input min-h-[90px]" required value={form.bio} onChange={set('bio')} />{err('bio')}</div>
              </div>
            )}
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
  const [mentorType, setMentorType] = useState('')
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
  const isMentors = fixedRole === 'mentor'
  // The mentor screen reads /mentors (it carries type/company details); rows are mapped to user ids for the account actions.
  const { items: raw, meta, loading, error, reload } = useList(isMentors ? userService.mentors : userService.list, {
    q: dq, role: fixedRole || role || undefined, page, mentor_type: isMentors ? mentorType || undefined : undefined,
  })
  const items = isMentors ? raw.map((m) => ({ ...m, id: m.user_id, role: 'mentor' })) : raw

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
          {isMentors && (
            <select className="input sm:order-2" aria-label="Filter by mentor type" value={mentorType} onChange={(e) => { setMentorType(e.target.value); setPage(1) }}>
              <option value="">All mentors</option><option value="internal">Internal (ICT trainers)</option><option value="industry">External (industry)</option>
            </select>
          )}
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
          ...(isMentors ? [
            { key: 'type', header: 'Type', render: (u) => <StatusBadge tone={u.mentor_type === 'industry' ? 'blue' : 'green'}>{u.mentor_type === 'industry' ? 'Industry' : 'Internal'}</StatusBadge> },
            { key: 'org', header: 'Company / sector', render: (u) => (u.mentor_type === 'industry'
              ? <div><div className="font-medium">{u.company}</div><div className="text-xs text-slate-500">{u.industry_sector}{u.designation ? ` · ${u.designation}` : ''}{u.linkedin_url && <> · <a className="text-brand underline" href={u.linkedin_url} target="_blank" rel="noopener noreferrer">Profile</a></>}</div></div>
              : <span className="text-slate-400">{u.designation || 'ICT trainer'}</span>) },
          ] : [{ key: 'role', header: 'Role', render: (u) => ROLE_LABEL[u.role] }]),
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
