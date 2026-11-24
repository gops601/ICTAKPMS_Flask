import { useEffect, useState } from 'react'
import { Download, KeyRound, Plus, Repeat, Trash2 } from 'lucide-react'
import { domainService, userService } from '../../services/adminService'
import { errorMessage, fieldErrors } from '../../services/api'
import { useDebounced, useList } from '../../hooks/useList'
import { ROLE_LABEL } from '../../utils/roles'
import { downloadStaffCredentials } from '../../utils/credentials'
import PageHeader from '../../components/PageHeader'
import DataTable from '../../components/DataTable'
import Pagination from '../../components/Pagination'
import Modal from '../../components/Modal'
import ConfirmDialog from '../../components/ConfirmDialog'
import MentorTransferModal from '../../components/MentorTransferModal'
import StatusBadge from '../../components/StatusBadge'
import Alert from '../../components/Alert'

function CreateUserModal({ domains, onClose, onDone, fixedRole }) {
  const [form, setForm] = useState({
    role: fixedRole || 'mentor', name: '', email: '', phone: '', domain_id: '', domain_ids: [], designation: '',
    mentor_type: 'internal', company: '', industry_sector: '', experience_years: '', linkedin_url: '', bio: '', also_mentor: false,
  })
  const [error, setError] = useState('')
  const [errs, setErrs] = useState({})
  const [busy, setBusy] = useState(false)
  const [created, setCreated] = useState(null)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const isMentor = form.role === 'mentor' || (form.role === 'admin' && form.also_mentor)

  const submit = async (e) => {
    e.preventDefault(); setError(''); setErrs({})
    if (form.role === 'domain_lead' && form.domain_ids.length === 0) { setErrs({ domain_ids: 'Select at least one domain' }); return setError('Choose the domain this lead will manage.') }
    setBusy(true)
    const body = { role: form.role, name: form.name, email: form.email, phone: form.phone || null }
    if (form.role === 'domain_lead') body.domain_ids = form.domain_ids
    if (form.role === 'admin' && form.also_mentor) body.also_mentor = true
    if (isMentor) {
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
  const industry = isMentor && form.mentor_type === 'industry'
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
        {form.role === 'domain_lead' && (
          <fieldset>
            <legend className="label">Domain(s) to lead *</legend>
            <div className="max-h-40 space-y-1 overflow-y-auto rounded-xl border border-slate-300 bg-white p-2">
              {domains.map((d) => (
                <label key={d.id} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={form.domain_ids.includes(d.id)}
                    onChange={(e) => setForm({ ...form, domain_ids: e.target.checked ? [...form.domain_ids, d.id] : form.domain_ids.filter((x) => x !== d.id) })} />
                  {d.name}
                </label>
              ))}
              {domains.length === 0 && <p className="text-xs text-slate-500">No active domains yet. Add a domain first.</p>}
            </div>
            {err('domain_ids')}
            <p className="mt-1 text-xs text-slate-500">The lead sees only these domains' batches and Project Shelf.</p>
          </fieldset>
        )}
        {form.role === 'admin' && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.also_mentor} onChange={(e) => setForm({ ...form, also_mentor: e.target.checked })} />
            Also add this administrator as a mentor
          </label>
        )}
        {isMentor && (
          <>
            <div><label htmlFor="u-dom" className="label">Domain *</label>
              <select id="u-dom" className="input" required value={form.domain_id} onChange={set('domain_id')}>
                <option value="">Select domain…</option>{domains.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>{err('domain_id')}</div>
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

/** Issues fresh temporary passwords for mentors / domain leads who have not logged in yet and offers them as one CSV. */
function StaffCredentialsModal({ role, onClose }) {
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [includeActive, setIncludeActive] = useState(false)
  const label = ROLE_LABEL[role]
  const issue = async () => {
    setBusy(true); setError('')
    try { setResult(await userService.credentials(role, undefined, includeActive)) } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  return (
    <Modal title={`Download ${label.toLowerCase()} credentials`} onClose={onClose} wide>
      {!result ? (
        <div className="space-y-4">
          <Alert>{error}</Alert>
          <p className="text-sm text-slate-600">
            Creates a <b>new temporary password</b> for every {label.toLowerCase()} who has not logged in yet and gives you a file with their login details to share.
            Passwords are shown once and are not stored in readable form.
          </p>
          <label className="flex items-start gap-2 rounded-lg bg-orange-50 p-3 text-sm text-orange-800">
            <input type="checkbox" className="mt-1" checked={includeActive} onChange={(e) => setIncludeActive(e.target.checked)} />
            <span>Also reissue for {label.toLowerCase()}s who already chose their own password. <b>Their current password stops working</b> and they must sign in with the new one. Leave unticked to skip them.</span>
          </label>
          <div className="flex justify-end gap-2">
            <button className="btn-secondary" onClick={onClose}>Cancel</button>
            <button className="btn-primary" disabled={busy} onClick={issue}><KeyRound className="h-4 w-4" />{busy ? 'Generating…' : 'Generate passwords'}</button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <Alert type={result.credentials.length ? 'success' : 'warning'}>
            {result.credentials.length ? `${result.credentials.length} ${label.toLowerCase()}(s) ready.` : 'No new passwords were issued.'}
            {result.skipped.length > 0 && ` ${result.skipped.length} skipped.`}
          </Alert>
          {result.credentials.length > 0 && (
            <>
              <Alert type="warning">Download now – these passwords cannot be shown again. They must change them at first login.</Alert>
              <button className="btn-primary" onClick={() => downloadStaffCredentials(result.credentials, `${role}_credentials.csv`)}>
                <Download className="h-4 w-4" />Download details with passwords (CSV)
              </button>
            </>
          )}
          {result.skipped.length > 0 && (
            <ul className="list-disc pl-5 text-sm text-slate-600" aria-label="Skipped users">
              {result.skipped.map((s) => <li key={s.email}>{s.name} ({s.email}) – {s.reason}</li>)}
            </ul>
          )}
          <div className="flex justify-end"><button className="btn-secondary" onClick={onClose}>Close</button></div>
        </div>
      )}
    </Modal>
  )
}

/** Set which domains a domain lead leads. A lead only ever sees the data of these domains. */
function LeadDomainsModal({ lead, domains, onClose, onSaved }) {
  const [selected, setSelected] = useState(new Set((lead.domains || []).map((d) => d.id)))
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const toggle = (id) => setSelected((cur) => { const n = new Set(cur); n.has(id) ? n.delete(id) : n.add(id); return n })
  const save = async () => {
    if (selected.size === 0) return setError('Choose at least one domain.')
    setBusy(true); setError('')
    try { await userService.setDomains(lead.id, [...selected]); onSaved() } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  return (
    <Modal title={`Domains – ${lead.name}`} onClose={onClose}
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" disabled={busy} onClick={save}>{busy ? 'Saving…' : 'Save'}</button></>}>
      <Alert>{error}</Alert>
      <p className="mb-2 text-sm text-slate-600">This lead sees only the batches, mentors, students, projects and Project Shelf of the domains ticked below.</p>
      <ul className="space-y-2">
        {domains.map((d) => (
          <li key={d.id}><label className="flex items-center gap-3 text-sm"><input type="checkbox" checked={selected.has(d.id)} onChange={() => toggle(d.id)} />{d.name}</label></li>
        ))}
      </ul>
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
  const [credentials, setCredentials] = useState(false)
  const [deleting, setDeleting] = useState(null)
  const [domainsFor, setDomainsFor] = useState(null)
  const [transfer, setTransfer] = useState(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const dq = useDebounced(q)

  useEffect(() => { domainService.list({ active: 1 }).then(setDomains).catch(() => {}) }, [])
  const isMentors = fixedRole === 'mentor'
  // The mentor screen reads /mentors (it carries type/company details); rows are mapped to user ids for the account actions.
  const { items: raw, meta, loading, error, reload } = useList(isMentors ? userService.mentors : userService.list, {
    q: dq, role: fixedRole || role || undefined, page, mentor_type: isMentors ? mentorType || undefined : undefined,
  })
  const items = isMentors ? raw.map((m) => ({ ...m, mentor_id: m.id, id: m.user_id, role: m.is_domain_lead ? 'domain_lead' : 'mentor' })) : raw

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

  const doDelete = async () => {
    setBusy(true); setActionError('')
    try { await userService.remove(deleting.id); setDeleting(null); reload() }
    catch (e) { setActionError(errorMessage(e)); setDeleting(null) } finally { setBusy(false) }
  }
  const credRole = fixedRole === 'mentor' || fixedRole === 'domain_lead' ? fixedRole : (role === 'mentor' || role === 'domain_lead' ? role : null)

  return (
    <div>
      <PageHeader title={title} subtitle={subtitle}
        actions={<>
          {credRole && <button className="btn-secondary" onClick={() => setCredentials(true)}><KeyRound className="h-4 w-4" />Download credentials</button>}
          <button className="btn-primary" onClick={() => setCreating(true)}><Plus className="h-4 w-4" />{addLabel}</button>
        </>} />
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
          ...(role === 'domain_lead' || fixedRole === 'domain_lead' ? [
            { key: 'domains', header: 'Domain(s)', render: (u) => (u.domains && u.domains.length
              ? u.domains.map((d) => d.name).join(', ')
              : <StatusBadge tone="orange">No domain – sees nothing</StatusBadge>) },
          ] : []),
          ...(isMentors ? [
            { key: 'type', header: 'Type', render: (u) => (u.is_domain_lead
              ? <StatusBadge tone="orange">Domain lead</StatusBadge>
              : <StatusBadge tone={u.mentor_type === 'industry' ? 'blue' : 'green'}>{u.mentor_type === 'industry' ? 'Industry' : 'Internal'}</StatusBadge>) },
            { key: 'org', header: 'Company / sector', render: (u) => (u.mentor_type === 'industry'
              ? <div><div className="font-medium">{u.company}</div><div className="text-xs text-slate-500">{u.industry_sector}{u.designation ? ` · ${u.designation}` : ''}{u.linkedin_url && <> · <a className="text-brand underline" href={u.linkedin_url} target="_blank" rel="noopener noreferrer">Profile</a></>}</div></div>
              : <span className="text-slate-400">{u.designation || 'ICT trainer'}</span>) },
          ] : [{ key: 'role', header: 'Role', render: (u) => ROLE_LABEL[u.role] }]),
          { key: 'status', header: 'Status', render: (u) => <StatusBadge status={u.is_active ? 'active' : 'inactive'} /> },
          { key: 'actions', header: 'Actions', render: (u) => (
            <div className="flex flex-wrap gap-2">
              <button className="btn-secondary" onClick={() => setResetFor(u)}><KeyRound className="h-4 w-4" />Reset password</button>
              {u.role === 'domain_lead' && <button className="btn-secondary" onClick={() => setDomainsFor(u)}>Domains</button>}
              {isMentors && <button className="btn-secondary" aria-label={`Replace or remove ${u.name}`} onClick={() => setTransfer({ id: u.mentor_id, name: u.name })}><Repeat className="h-4 w-4" />Replace / remove</button>}
              <button className="btn-secondary" onClick={() => setToggle(u)}>{u.is_active ? 'Deactivate' : 'Activate'}</button>
              <button className="btn-danger" onClick={() => { setActionError(''); setDeleting(u) }} aria-label={`Delete ${u.name}`}><Trash2 className="h-4 w-4" />Delete</button>
            </div>
          ) },
        ]} />
        <Pagination meta={meta} onPage={setPage} />
      </div>
      {creating && <CreateUserModal fixedRole={fixedRole} domains={domains} onClose={() => setCreating(false)} onDone={() => { setCreating(false); reload() }} />}
      {resetFor && <ConfirmDialog message={`Reset the password for ${resetFor.name}? A new temporary password will be generated.`} confirmLabel="Reset password" busy={busy} onConfirm={doReset} onCancel={() => setResetFor(null)} />}
      {toggle && <ConfirmDialog message={`${toggle.is_active ? 'Deactivate' : 'Activate'} ${toggle.name}?`} confirmLabel={toggle.is_active ? 'Deactivate' : 'Activate'} danger={toggle.is_active} busy={busy} onConfirm={doToggle} onCancel={() => setToggle(null)} />}
      {domainsFor && <LeadDomainsModal lead={domainsFor} domains={domains} onClose={() => setDomainsFor(null)} onSaved={() => { setDomainsFor(null); reload() }} />}
      {transfer && <MentorTransferModal mentor={transfer} onClose={() => setTransfer(null)} onDone={() => { setTransfer(null); reload() }} />}
      {credentials && credRole && <StaffCredentialsModal role={credRole} onClose={() => setCredentials(false)} />}
      {deleting && <ConfirmDialog danger confirmLabel="Delete permanently" busy={busy} onConfirm={doDelete} onCancel={() => setDeleting(null)}
        message={`Permanently delete ${deleting.name} (${deleting.email})? This cannot be undone. If they have work attached you will be asked to deactivate instead.`} />}
      {tempPw && (
        <Modal title="Password reset" onClose={() => setTempPw(null)}>
          <Alert type="warning">Temporary password for {tempPw.user.email} (shown once): <b className="font-mono">{tempPw.password}</b></Alert>
          <div className="mt-4 flex flex-wrap justify-end gap-2">
            <button className="btn-secondary" onClick={() => downloadStaffCredentials([{ name: tempPw.user.name, email: tempPw.user.email, phone: tempPw.user.phone || '', role: tempPw.user.role, designation: tempPw.user.designation || '', company: tempPw.user.company || '', details: '', temporary_password: tempPw.password }], `${tempPw.user.email.split('@')[0]}_login_details.csv`)}>
              <Download className="h-4 w-4" />Download login details
            </button>
            <button className="btn-primary" onClick={() => setTempPw(null)}>Done</button>
          </div>
        </Modal>
      )}
    </div>
  )
}
