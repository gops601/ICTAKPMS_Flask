import { useRef, useState } from 'react'
import { Download, Trash2, Upload } from 'lucide-react'
import { psService } from '../services/adminService'
import { errorMessage } from '../services/api'
import Alert from './Alert'
import ConfirmDialog from './ConfirmDialog'

const fmtSize = (b) => (b >= 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`)

/** Datasets or reference documents for one problem statement. `canEdit` toggles upload/delete. */
export default function AttachmentPanel({ psId, kind, title, hint, items, canEdit, onChanged }) {
  const fileRef = useRef(null)
  const [desc, setDesc] = useState('')
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [removing, setRemoving] = useState(null)

  const upload = async () => {
    if (!file) return setError('Choose a file first.')
    setBusy(true); setError('')
    try {
      await psService.upload(psId, kind, file, desc)
      setFile(null); setDesc('')
      if (fileRef.current) fileRef.current.value = ''
      onChanged()
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  const download = async (item) => {
    setError('')
    try { await psService.download(psId, kind, item) } catch (e) { setError(errorMessage(e, 'Download failed')) }
  }
  const remove = async () => {
    setBusy(true)
    try { await psService.removeFile(psId, kind, removing.id); setRemoving(null); onChanged() }
    catch (e) { setError(errorMessage(e)); setRemoving(null) } finally { setBusy(false) }
  }

  return (
    <section className="card space-y-3" aria-label={title}>
      <div>
        <h3 className="font-semibold text-slate-900">{title}</h3>
        {hint && <p className="text-xs text-slate-500">{hint}</p>}
      </div>
      <Alert>{error}</Alert>
      {items.length === 0 && <p className="text-sm text-slate-500">Nothing attached yet.</p>}
      <ul className="divide-y divide-slate-100">
        {items.map((it) => (
          <li key={it.id} className="flex items-center justify-between gap-3 py-2 text-sm">
            <div className="min-w-0">
              <div className="truncate font-medium">{it.name}</div>
              <div className="text-xs text-slate-500">{fmtSize(it.size_bytes)}{it.description ? ` · ${it.description}` : ''}</div>
            </div>
            <div className="flex shrink-0 gap-2">
              <button className="btn-secondary" onClick={() => download(it)} aria-label={`Download ${it.name}`}><Download className="h-4 w-4" /></button>
              {canEdit && <button className="btn-secondary" onClick={() => setRemoving(it)} aria-label={`Delete ${it.name}`}><Trash2 className="h-4 w-4" /></button>}
            </div>
          </li>
        ))}
      </ul>
      {canEdit && (
        <div className="grid grid-cols-1 gap-2 rounded-lg bg-slate-50 p-3 sm:grid-cols-3">
          <input ref={fileRef} type="file" aria-label={`Choose ${title} file`} className="text-sm sm:col-span-1" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          <input className="input" placeholder="Description (optional)" aria-label={`${title} description`} value={desc} onChange={(e) => setDesc(e.target.value)} />
          <button className="btn-primary" onClick={upload} disabled={busy}><Upload className="h-4 w-4" />{busy ? 'Uploading…' : 'Upload'}</button>
        </div>
      )}
      {removing && <ConfirmDialog danger confirmLabel="Delete file" busy={busy} message={`Permanently delete “${removing.name}”?`} onConfirm={remove} onCancel={() => setRemoving(null)} />}
    </section>
  )
}
