import { useEffect, useState } from 'react'
import { Download, FileUp } from 'lucide-react'
import { downloadFile, importService, ouService } from '../services/adminService'
import { downloadCredentials } from '../utils/credentials'
import { errorMessage } from '../services/api'
import PageHeader from './PageHeader'
import DataTable from './DataTable'
import StatusBadge from './StatusBadge'
import ConfirmDialog from './ConfirmDialog'
import Alert from './Alert'

const MAX_BYTES = 5 * 1024 * 1024

/**
 * Select OU -> download template -> upload -> preview/validate -> confirm -> summary.
 * `type` is 'batches' or 'students'; everything else comes from the API.
 */
export default function ImportWizard({ type, title, subtitle, embedded = false }) {
  const needsOu = type === 'batches' || type === 'students'
  const [ous, setOus] = useState([])
  const [ouId, setOuId] = useState('')
  const [file, setFile] = useState(null)
  const [job, setJob] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirmPartial, setConfirmPartial] = useState(false)

  useEffect(() => {
    // Preselect the first OU so the template buttons are usable straight away.
    if (!needsOu) return undefined
    ouService.list({ active: 1 }).then((list) => { setOus(list); setOuId((cur) => cur || (list[0] ? String(list[0].id) : '')) })
      .catch((e) => setError(errorMessage(e)))
    return undefined
  }, [needsOu])

  const reset = () => { setJob(null); setResult(null); setFile(null); setError('') }

  const onFile = (e) => {
    const f = e.target.files?.[0]
    setError('')
    if (f && f.size > MAX_BYTES) { setError('File is too large (max 5 MB).'); e.target.value = ''; return }
    setFile(f || null)
  }

  const template = async (format) => {
    if (needsOu && !ouId) return setError('Select an OU first to get its template.')
    setError('')
    try {
      if (needsOu) await downloadFile(`/ous/${ouId}/template`, { type, format }, `${type}_template.${format}`)
      else await downloadFile('/problem-statements/template', { format }, `${type}_template.${format}`)
    }
    catch (e) { setError(errorMessage(e, 'Download failed')) }
  }

  const upload = async () => {
    if (needsOu && !ouId) return setError('Select an OU first.')
    if (!file) return setError('Choose a .csv or .xlsx file to upload.')
    setBusy(true); setError(''); setJob(null)
    try { setJob(await importService.upload(type, needsOu ? ouId : null, file)) } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }

  const confirm = async (validOnly) => {
    setBusy(true); setError(''); setConfirmPartial(false)
    try { setResult(await importService.confirm(job.id, validOnly)) } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }

  const errorReport = async (id = job.id) => {
    try { await downloadFile(`/imports/${id}/errors.csv`, undefined, `import_${id}_errors.csv`) }
    catch (e) { setError(errorMessage(e, 'Download failed')) }
  }

  if (result) {
    return (
      <div>
        <PageHeader title={title} />
        <div className="card space-y-3">
          <Alert type="success">{result.imported_rows} record(s) imported successfully.{result.error_rows ? ` ${result.error_rows} invalid row(s) were skipped.` : ''}</Alert>
          <dl className="grid grid-cols-3 gap-4 text-sm">
            <div><dt className="text-slate-500">Rows in file</dt><dd className="text-lg font-semibold">{result.total_rows}</dd></div>
            <div><dt className="text-slate-500">Imported</dt><dd className="text-lg font-semibold text-green-700">{result.imported_rows}</dd></div>
            <div><dt className="text-slate-500">Skipped</dt><dd className="text-lg font-semibold text-red-700">{result.error_rows}</dd></div>
          </dl>
          {result.credentials && (
            <Alert type="warning">
              Temporary passwords are shown only once. Download the student details with their passwords now and share them securely; students must change the password at first login. (Later, use Students → Download credentials to issue new ones.)
              <div className="mt-2">
                <button className="btn-primary" onClick={() => downloadCredentials(result.credentials)}>
                  <Download className="h-4 w-4" />Download student details with passwords (CSV)
                </button>
              </div>
            </Alert>
          )}
          <div className="flex gap-2">
            {result.error_rows > 0 && <button className="btn-secondary" onClick={() => errorReport(result.id)}>Download error report</button>}
            <button className="btn-primary" onClick={reset}>Import another file</button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {!embedded && <PageHeader title={title} subtitle={subtitle} />}
      <div className="card space-y-4">
        <Alert>{error}</Alert>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {needsOu && (
            <div>
              <label htmlFor="imp-ou" className="label">1. Select OU</label>
              <select id="imp-ou" className="input" value={ouId} onChange={(e) => { setOuId(e.target.value); setJob(null) }}>
                <option value="">Select OU…</option>{ous.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
              </select>
            </div>
          )}
          <div>
            <span className="label">2. Download template</span>
            <div className="flex gap-2">
              <button className="btn-secondary" onClick={() => template('xlsx')}><Download className="h-4 w-4" />Excel</button>
              <button className="btn-secondary" onClick={() => template('csv')}><Download className="h-4 w-4" />CSV</button>
            </div>
          </div>
        </div>
        <div>
          <label htmlFor="imp-file" className="label">3. Upload completed file (.csv or .xlsx, max 5 MB)</label>
          <div className="flex flex-wrap items-center gap-3">
            <input id="imp-file" type="file" accept=".csv,.xlsx" onChange={onFile} className="text-sm" />
            <button className="btn-primary" disabled={busy} onClick={upload}>
              <FileUp className="h-4 w-4" />{busy && !job ? 'Validating…' : 'Upload & validate'}
            </button>
          </div>
        </div>
      </div>

      {job && (
        <div className="card space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex gap-6 text-sm">
              <span>Total rows: <b>{job.total_rows}</b></span>
              <span className="text-green-700">Valid: <b>{job.valid_rows}</b></span>
              <span className="text-red-700">Errors: <b>{job.error_rows}</b></span>
            </div>
            <div className="flex flex-wrap gap-2">
              {job.error_rows > 0 && <button className="btn-secondary" onClick={() => errorReport()}><Download className="h-4 w-4" />Error report</button>}
              {job.error_rows > 0 && job.valid_rows > 0 && (
                <button className="btn-secondary" disabled={busy} onClick={() => setConfirmPartial(true)}>Import valid rows only</button>
              )}
              <button className="btn-primary" disabled={busy || job.error_rows > 0 || job.valid_rows === 0} onClick={() => confirm(false)}>
                {busy ? 'Importing…' : 'Confirm import'}
              </button>
            </div>
          </div>
          {job.error_rows > 0 && <Alert type="warning">Some rows failed validation. Fix the file and re-upload, or explicitly import only the valid rows.</Alert>}
          {job.ignored_columns?.length > 0 && <Alert type="info">Ignored unrecognised columns: {job.ignored_columns.join(', ')}</Alert>}
          <DataTable rowKey="row_number" rows={job.preview} empty="Nothing to preview" columns={[
            { key: 'row_number', header: 'Row' },
            { key: 'status', header: 'Status', render: (r) => <StatusBadge status={r.status} /> },
            { key: 'data', header: 'Data', render: (r) => <span className="text-xs text-slate-600">{Object.values(r.data).filter(Boolean).join(' · ')}</span> },
            { key: 'errors', header: 'Problems', render: (r) => r.errors.length ? (
              <ul className="list-disc pl-4 text-xs text-red-700">{r.errors.map((e, i) => <li key={i}>{e.message}</li>)}</ul>
            ) : '—' },
          ]} />
          {job.total_rows > job.preview.length && <p className="text-xs text-slate-500">Showing the first {job.preview.length} rows. The error report contains every failed row.</p>}
        </div>
      )}
      {confirmPartial && (
        <ConfirmDialog title="Import valid rows only?" confirmLabel="Import valid rows" busy={busy}
          message={`${job.error_rows} invalid row(s) will NOT be imported. ${job.valid_rows} valid row(s) will be.`}
          onConfirm={() => confirm(true)} onCancel={() => setConfirmPartial(false)} />
      )}
    </div>
  )
}
