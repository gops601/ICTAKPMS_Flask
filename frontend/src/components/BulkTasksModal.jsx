import { useState } from 'react'
import { Download, FileUp } from 'lucide-react'
import { scrumService } from '../services/adminService'
import { errorMessage } from '../services/api'
import Modal from './Modal'
import Alert from './Alert'

/** Weekly bulk task upload: download the template, fill it in, upload. Nothing is added unless every row is valid. */
export default function BulkTasksModal({ projectId, onClose, onDone }) {
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  const template = async (format) => {
    setError('')
    try { await scrumService.bulkTemplate(projectId, format) } catch (e) { setError(errorMessage(e)) }
  }
  const upload = async () => {
    if (!file) return setError('Choose the filled template first.')
    setBusy(true); setError(''); setResult(null)
    try {
      const r = await scrumService.bulkUpload(projectId, file)
      setResult(r)
      if (r.created) onDone(r.board)
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }

  return (
    <Modal title="Upload this week's tasks" onClose={onClose} wide
      footer={result?.created
        ? <button className="btn-primary" onClick={onClose}>Done</button>
        : <><button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={busy || !file} onClick={upload}><FileUp className="h-4 w-4" />{busy ? 'Uploading…' : 'Upload tasks'}</button></>}>
      <div className="space-y-4">
        <Alert>{error}</Alert>
        {result?.created > 0 && <Alert type="success">{result.created} task(s) were added to the board.</Alert>}
        {result && result.created === 0 && result.errors.length > 0 && (
          <Alert type="warning">
            Nothing was added. Fix these rows and upload again:
            <ul className="mt-1 list-disc pl-5" aria-label="Row errors">
              {result.errors.map((e) => <li key={e.row}>Row {e.row}: {e.message}</li>)}
            </ul>
          </Alert>
        )}
        <div>
          <span className="label">1. Download the template</span>
          <div className="flex gap-2">
            <button className="btn-secondary" onClick={() => template('xlsx')}><Download className="h-4 w-4" />Excel</button>
            <button className="btn-secondary" onClick={() => template('csv')}><Download className="h-4 w-4" />CSV</button>
          </div>
          <p className="mt-1 text-xs text-slate-500">One row per task. Week (1, 2, …) fills the start and due dates for you; Assigned To takes team members&apos; emails or registration numbers, separated by commas. Remove the example row. Up to 200 tasks.</p>
        </div>
        <div>
          <label htmlFor="bulk-file" className="label">2. Upload the filled file (.xlsx or .csv)</label>
          <input id="bulk-file" type="file" accept=".csv,.xlsx" className="text-sm" onChange={(e) => { setFile(e.target.files?.[0] || null); setResult(null) }} />
        </div>
      </div>
    </Modal>
  )
}
