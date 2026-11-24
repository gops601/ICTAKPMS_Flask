import { useCallback, useEffect, useState } from 'react'
import { BookOpen, Copy, Download, KeyRound, Plug, RefreshCw, Trash2 } from 'lucide-react'
import { ouService, portalService } from '../../services/adminService'
import { errorMessage } from '../../services/api'
import PageHeader from '../../components/PageHeader'
import Alert from '../../components/Alert'
import Modal from '../../components/Modal'
import ConfirmDialog from '../../components/ConfirmDialog'
import Spinner from '../../components/Spinner'
import StatusBadge from '../../components/StatusBadge'

const EMPTY = { name: '', base_url: '', enrollment_path: '/api/enrollments', api_token: '', default_ou_id: '' }
const fmt = (iso) => (iso ? new Date(`${iso}Z`).toLocaleString() : 'never')

function PortalForm({ portal, ous, onClose, onSaved }) {
  const [form, setForm] = useState(portal ? { ...EMPTY, ...portal, api_token: '', default_ou_id: portal.default_ou_id || '' } : EMPTY)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const save = async (e) => {
    e.preventDefault(); setBusy(true); setError('')
    const body = { name: form.name, base_url: form.base_url || null, enrollment_path: form.enrollment_path || null, api_token: form.api_token || null,
      default_ou_id: form.default_ou_id ? Number(form.default_ou_id) : null }
    try { onSaved(portal ? await portalService.update(portal.id, body) : await portalService.create(body), !portal) } catch (err) { setError(errorMessage(err)) } finally { setBusy(false) }
  }
  return (
    <Modal title={portal ? `Edit ${portal.name}` : 'Connect a portal'} onClose={onClose}>
      <form onSubmit={save} className="space-y-3">
        <Alert>{error}</Alert>
        <div><label htmlFor="po-name" className="label">Portal name *</label><input id="po-name" className="input" required value={form.name} onChange={set('name')} /></div>
        <div><label htmlFor="po-url" className="label">Portal base URL <span className="font-normal text-slate-500">(only to pull enrolments)</span></label>
          <input id="po-url" className="input" placeholder="https://learn.example.org" value={form.base_url || ''} onChange={set('base_url')} /></div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div><label htmlFor="po-path" className="label">Enrolment feed path</label><input id="po-path" className="input" value={form.enrollment_path || ''} onChange={set('enrollment_path')} /></div>
          <div><label htmlFor="po-token" className="label">API token {portal?.has_api_token && <span className="font-normal text-slate-500">(saved – leave blank to keep)</span>}</label>
            <input id="po-token" type="password" autoComplete="off" className="input" value={form.api_token} onChange={set('api_token')} /></div>
        </div>
        <div><label htmlFor="po-ou" className="label">Organisational unit for new batches</label>
          <select id="po-ou" className="input" value={form.default_ou_id} onChange={set('default_ou_id')}>
            <option value="">First active OU</option>{ous.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}</select></div>
        <div className="flex justify-end gap-2"><button type="button" className="btn-secondary" onClick={onClose}>Cancel</button><button className="btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button></div>
      </form>
    </Modal>
  )
}

function SecretDialog({ portal, onClose }) {
  const copy = (text) => navigator.clipboard?.writeText(text).catch(() => {})
  return (
    <Modal title="Give these details to the other portal" onClose={onClose} footer={<button className="btn-primary" onClick={onClose}>Done</button>}>
      <div className="space-y-3 text-sm">
        <div className="flex flex-wrap gap-2">
          <button className="btn-secondary" onClick={() => portalService.config(portal, 'json', portal.shared_secret).catch(() => {})}><Download className="h-4 w-4" />Configuration file (JSON, with secret)</button>
          <button className="btn-secondary" onClick={() => portalService.config(portal, 'env', portal.shared_secret).catch(() => {})}><Download className="h-4 w-4" />.env file (with secret)</button>
          <button className="btn-secondary" onClick={() => portalService.guide().catch(() => {})}><BookOpen className="h-4 w-4" />Integration guide</button>
        </div>
        <Alert type="warning">The shared secret is shown only now. Copy it and store it safely; you can issue a new one later.</Alert>
        {[['Shared secret', portal.shared_secret], ['Portal ID (slug)', portal.slug], ['Sign-in endpoint', portal.sso_endpoint], ['Enrolment push endpoint', portal.push_endpoint]].map(([l, v]) => (
          <div key={l}><div className="label">{l}</div>
            <div className="flex items-center gap-2"><code className="min-w-0 flex-1 break-all rounded bg-slate-100 px-2 py-1 text-xs">{v}</code>
              <button className="btn-secondary" aria-label={`Copy ${l}`} onClick={() => copy(v)}><Copy className="h-4 w-4" /></button></div></div>
        ))}
      </div>
    </Modal>
  )
}

/** Admin: connect other portals for single sign-on and for enrolling batches/students automatically. */
export default function PortalConnections() {
  const [portals, setPortals] = useState(null)
  const [ous, setOus] = useState([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [editing, setEditing] = useState(null) // 'new' | portal
  const [secret, setSecret] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [busyId, setBusyId] = useState(null)

  const load = useCallback(() => portalService.list().then(setPortals).catch((e) => setError(errorMessage(e))), [])
  useEffect(() => { load(); ouService.list({ per_page: 100 }).then((r) => setOus(r.items || r)).catch(() => {}) }, [load])

  const run = async (id, fn, ok) => {
    setBusyId(id); setError(''); setNotice('')
    try { const r = await fn(); if (ok) setNotice(ok(r)); await load(); return r } catch (e) { setError(errorMessage(e)) } finally { setBusyId(null) }
  }
  const sync = (p) => run(p.id, () => portalService.sync(p.id), (r) => { const s = r.last_sync_summary; return `Synced ${p.name}: ${s.batches_created} new batch(es), ${s.students_created} new student(s)${s.problems.length ? `, ${s.problems.length} problem(s)` : ''}.` })
  const rotate = async (p) => { const r = await run(p.id, () => portalService.rotateSecret(p.id)); if (r) setSecret(r) }
  const remove = async () => { await run(deleting.id, () => portalService.remove(deleting.id), () => `${deleting.name} disconnected.`); setDeleting(null) }

  return (
    <div className="space-y-4">
      <PageHeader title="Portal Connections" subtitle="Connect another portal so its students can sign in here (SSO) and its batches and students are enrolled automatically."
        actions={<>
          <button className="btn-secondary" onClick={() => portalService.guide().catch((e) => setError(errorMessage(e, 'Download failed')))}><BookOpen className="h-4 w-4" />Integration guide</button>
          <a className="btn-secondary" href="/api/docs" target="_blank" rel="noreferrer">API documentation</a>
          <button className="btn-primary" onClick={() => setEditing('new')}><Plug className="h-4 w-4" />Connect a portal</button>
        </>} />
      <Alert>{error}</Alert>
      {notice && <Alert type="success">{notice}</Alert>}
      {portals === null ? <Spinner /> : portals.length === 0 ? <div className="card text-sm text-slate-500">No portals connected yet.</div> : portals.map((p) => {
        const s = p.last_sync_summary
        return (
          <section key={p.id} className="card space-y-2" aria-label={p.name}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2"><h2 className="font-semibold text-slate-900">{p.name}</h2><span className="font-mono text-xs text-slate-500">{p.slug}</span>
                <StatusBadge tone={p.is_active ? 'green' : 'grey'}>{p.is_active ? 'Active' : 'Off'}</StatusBadge></div>
              <div className="flex flex-wrap gap-2">
                <button className="btn-secondary" disabled={busyId === p.id || !p.base_url} title={p.base_url ? '' : 'Add a base URL to pull'} onClick={() => sync(p)}><RefreshCw className="h-4 w-4" />Sync now</button>
                <button className="btn-secondary" aria-label={`Download configuration for ${p.name}`} onClick={() => portalService.config(p, 'json').catch((e) => setError(errorMessage(e, 'Download failed')))}><Download className="h-4 w-4" />Configuration</button>
                <button className="btn-secondary" onClick={() => setEditing(p)}>Edit</button>
                <button className="btn-secondary" disabled={busyId === p.id} onClick={() => rotate(p)}><KeyRound className="h-4 w-4" />New secret</button>
                <button className="btn-danger" aria-label={`Disconnect ${p.name}`} onClick={() => setDeleting(p)}><Trash2 className="h-4 w-4" />Disconnect</button>
              </div>
            </div>
            <dl className="grid grid-cols-1 gap-1 text-xs text-slate-600 sm:grid-cols-2">
              <div><dt className="inline text-slate-500">Enrolled batches: </dt><dd className="inline font-medium">{p.batch_count}</dd></div>
              <div><dt className="inline text-slate-500">Last sync: </dt><dd className="inline font-medium">{fmt(p.last_sync_at)}</dd></div>
              <div className="sm:col-span-2"><dt className="inline text-slate-500">Push enrolments to: </dt><dd className="inline break-all font-mono">{p.push_endpoint}</dd></div>
              <div className="sm:col-span-2"><dt className="inline text-slate-500">Send students to: </dt><dd className="inline break-all font-mono">{p.sso_login_url}</dd></div>
            </dl>
            {s && <p className="text-xs text-slate-600">Last result: {s.batches_created} batch(es) created, {s.batches_updated} updated, {s.students_created} student(s) added, {s.students_updated} updated.</p>}
            {s?.problems?.length > 0 && <ul className="list-disc pl-5 text-xs text-orange-700" aria-label="Sync problems">{s.problems.slice(0, 10).map((m, i) => <li key={i}>{m}</li>)}</ul>}
          </section>
        )
      })}
      {editing && <PortalForm portal={editing === 'new' ? null : editing} ous={ous} onClose={() => setEditing(null)}
        onSaved={(p, created) => { setEditing(null); load(); if (created) setSecret(p) }} />}
      {secret && <SecretDialog portal={secret} onClose={() => setSecret(null)} />}
      {deleting && <ConfirmDialog danger confirmLabel="Disconnect" message={`Disconnect “${deleting.name}”? Its students can no longer sign in through it. Batches and students already enrolled stay.`} onConfirm={remove} onCancel={() => setDeleting(null)} />}
    </div>
  )
}
