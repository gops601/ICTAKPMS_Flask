import { useCallback, useEffect, useState } from 'react'
import { Download, Pencil, Plus, Settings2, Trash2 } from 'lucide-react'
import { ouService, downloadFile } from '../../services/adminService'
import { errorMessage, fieldErrors } from '../../services/api'
import PageHeader from '../../components/PageHeader'
import DataTable from '../../components/DataTable'
import Modal from '../../components/Modal'
import ConfirmDialog from '../../components/ConfirmDialog'
import StatusBadge from '../../components/StatusBadge'
import Alert from '../../components/Alert'

const FIELD_TYPES = ['text', 'number', 'date', 'email', 'select']

function OUFormModal({ ou, onClose, onSaved }) {
  const [form, setForm] = useState({ name: ou?.name || '', code: ou?.code || '', description: ou?.description || '' })
  const [error, setError] = useState('')
  const [errs, setErrs] = useState({})
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError(''); setErrs({})
    try {
      if (ou) await ouService.update(ou.id, { name: form.name, description: form.description })
      else await ouService.create(form)
      onSaved()
    } catch (err) {
      setError(errorMessage(err)); setErrs(fieldErrors(err))
    } finally { setBusy(false) }
  }

  return (
    <Modal title={ou ? 'Edit OU' : 'Add OU'} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <Alert>{error}</Alert>
        <div>
          <label htmlFor="ou-name" className="label">Name</label>
          <input id="ou-name" className="input" required value={form.name} onChange={set('name')} />
          {errs.name && <p className="mt-1 text-xs text-red-600">{errs.name}</p>}
        </div>
        <div>
          <label htmlFor="ou-code" className="label">Code</label>
          <input id="ou-code" className="input" required disabled={Boolean(ou)} value={form.code} onChange={set('code')} />
          {errs.code && <p className="mt-1 text-xs text-red-600">{errs.code}</p>}
        </div>
        <div>
          <label htmlFor="ou-desc" className="label">Description</label>
          <textarea id="ou-desc" className="input" rows={3} value={form.description} onChange={set('description')} />
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
        </div>
      </form>
    </Modal>
  )
}

function FieldsModal({ ou, onClose }) {
  const [fields, setFields] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const blank = { label: '', scope: 'batch', field_type: 'text', is_required: false, options: '' }
  const [form, setForm] = useState(blank)

  const load = useCallback(async () => {
    setLoading(true)
    try { setFields(await ouService.fields(ou.id)) } catch (e) { setError(errorMessage(e)) } finally { setLoading(false) }
  }, [ou.id])
  useEffect(() => { load() }, [load])

  const add = async (e) => {
    e.preventDefault(); setError('')
    try {
      const body = { ...form, options: form.field_type === 'select' ? form.options.split(',').map((s) => s.trim()).filter(Boolean) : undefined }
      await ouService.addField(ou.id, body)
      setForm(blank); load()
    } catch (err) { setError(errorMessage(err)) }
  }

  const patch = async (f, body) => {
    setError('')
    try { await ouService.updateField(f.id, body); load() } catch (err) { setError(errorMessage(err)) }
  }

  return (
    <Modal title={`Registration fields – ${ou.name}`} onClose={onClose} wide>
      <div className="space-y-4">
        <Alert>{error}</Alert>
        <p className="text-sm text-slate-500">
          These fields drive the batch form, the batch import template and the student import template for this OU.
          Deactivated fields are hidden but existing data is kept.
        </p>
        <DataTable
          loading={loading}
          rows={fields}
          columns={[
            { key: 'label', header: 'Label' },
            { key: 'scope', header: 'Applies to' },
            { key: 'field_type', header: 'Type', render: (f) => f.field_type + (f.options ? ` (${f.options.join(', ')})` : '') },
            { key: 'req', header: 'Required', render: (f) => (
              <input type="checkbox" aria-label={`Required ${f.label}`} checked={f.is_required} onChange={(e) => patch(f, { is_required: e.target.checked })} />
            ) },
            { key: 'act', header: 'Active', render: (f) => (
              <input type="checkbox" aria-label={`Active ${f.label}`} checked={f.is_active} onChange={(e) => patch(f, { is_active: e.target.checked })} />
            ) },
          ]}
        />
        <form onSubmit={add} className="grid grid-cols-1 gap-3 rounded-lg bg-slate-50 p-3 sm:grid-cols-6">
          <div className="sm:col-span-2">
            <label htmlFor="fl" className="label">New field label</label>
            <input id="fl" className="input" required value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
          </div>
          <div>
            <label htmlFor="fs" className="label">Applies to</label>
            <select id="fs" className="input" value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value })}>
              <option value="batch">Batch</option><option value="student">Student</option>
            </select>
          </div>
          <div>
            <label htmlFor="ft" className="label">Type</label>
            <select id="ft" className="input" value={form.field_type} onChange={(e) => setForm({ ...form, field_type: e.target.value })}>
              {FIELD_TYPES.map((t) => <option key={t}>{t}</option>)}
            </select>
          </div>
          {form.field_type === 'select' && (
            <div className="sm:col-span-2">
              <label htmlFor="fo" className="label">Options (comma separated)</label>
              <input id="fo" className="input" value={form.options} onChange={(e) => setForm({ ...form, options: e.target.value })} />
            </div>
          )}
          <label className="flex items-center gap-2 pt-6 text-sm">
            <input type="checkbox" checked={form.is_required} onChange={(e) => setForm({ ...form, is_required: e.target.checked })} /> Required
          </label>
          <div className="flex items-end"><button className="btn-primary" type="submit"><Plus className="h-4 w-4" />Add field</button></div>
        </form>
      </div>
    </Modal>
  )
}

export default function OUManagement() {
  const [ous, setOus] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(null) // null | 'new' | ou
  const [fieldsFor, setFieldsFor] = useState(null)
  const [toggle, setToggle] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try { setOus(await ouService.list()) } catch (e) { setError(errorMessage(e)) } finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])

  const confirmToggle = async () => {
    setBusy(true)
    try { await ouService.setActive(toggle.id, !toggle.is_active); setToggle(null); load() }
    catch (e) { setError(errorMessage(e)); setToggle(null) } finally { setBusy(false) }
  }

  const template = async (ou, type, format) => {
    try { await downloadFile(`/ous/${ou.id}/template`, { type, format }, `${ou.code}_${type}.${format}`) }
    catch (e) { setError(errorMessage(e, 'Download failed')) }
  }

  return (
    <div>
      <PageHeader title="Organisational Units" subtitle="Manage OUs and configure their registration fields and import templates."
        actions={<button className="btn-primary" onClick={() => setEditing('new')}><Plus className="h-4 w-4" />Add OU</button>} />
      <Alert>{error}</Alert>
      <div className="card mt-3">
        <DataTable loading={loading} rows={ous} columns={[
          { key: 'name', header: 'Name' },
          { key: 'code', header: 'Code' },
          { key: 'status', header: 'Status', render: (o) => <StatusBadge status={o.is_active ? 'active' : 'inactive'} /> },
          { key: 'actions', header: 'Actions', render: (o) => (
            <div className="flex flex-wrap gap-2">
              <button className="btn-secondary" onClick={() => setEditing(o)}><Pencil className="h-4 w-4" />Edit</button>
              <button className="btn-secondary" onClick={() => setFieldsFor(o)}><Settings2 className="h-4 w-4" />Fields</button>
              <button className="btn-secondary" onClick={() => template(o, 'batches', 'xlsx')} title="Batch template (Excel)"><Download className="h-4 w-4" />Batch .xlsx</button>
              <button className="btn-secondary" onClick={() => template(o, 'batches', 'csv')}><Download className="h-4 w-4" />Batch .csv</button>
              <button className="btn-secondary" onClick={() => template(o, 'students', 'xlsx')}><Download className="h-4 w-4" />Student .xlsx</button>
              <button className="btn-secondary" onClick={() => template(o, 'students', 'csv')}><Download className="h-4 w-4" />Student .csv</button>
              <button className="btn-secondary" onClick={() => setToggle(o)}>{o.is_active ? 'Deactivate' : 'Activate'}</button>
              <button className="btn-danger" aria-label={`Delete ${o.name}`} onClick={() => { setError(''); setDeleting(o) }}><Trash2 className="h-4 w-4" />Delete</button>
            </div>
          ) },
        ]} />
      </div>
      {editing && <OUFormModal ou={editing === 'new' ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load() }} />}
      {fieldsFor && <FieldsModal ou={fieldsFor} onClose={() => setFieldsFor(null)} />}
      {deleting && (
        <ConfirmDialog danger confirmLabel="Delete permanently" busy={busy} onCancel={() => setDeleting(null)}
          message={`Permanently delete ${deleting.name} (${deleting.code}) and its registration fields? This cannot be undone. An OU that has batches cannot be deleted (deactivate it instead).`}
          onConfirm={async () => {
            setBusy(true)
            try { await ouService.remove(deleting.id); setDeleting(null); load() }
            catch (e) { setError(errorMessage(e)); setDeleting(null) } finally { setBusy(false) }
          }} />
      )}
      {toggle && (
        <ConfirmDialog
          message={toggle.is_active ? `Deactivate ${toggle.name}? No new batches can be created under it.` : `Activate ${toggle.name}?`}
          confirmLabel={toggle.is_active ? 'Deactivate' : 'Activate'} danger={toggle.is_active} busy={busy}
          onConfirm={confirmToggle} onCancel={() => setToggle(null)} />
      )}
    </div>
  )
}
