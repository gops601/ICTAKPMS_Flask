import { useEffect, useState } from 'react'
import { Download, FileSpreadsheet } from 'lucide-react'
import { batchService, domainService, ouService, reportService } from '../../services/adminService'
import { errorMessage } from '../../services/api'
import { useAuth } from '../../context/AuthContext'
import PageHeader from '../../components/PageHeader'
import Pagination from '../../components/Pagination'
import Alert from '../../components/Alert'
import Spinner from '../../components/Spinner'

const STAGES = [['allocated', 'Project Allocated'], ['srs_preparation', 'SRS Preparation'], ['srs_submitted', 'SRS Submitted'], ['srs_under_review', 'SRS Under Review'],
  ['srs_changes_requested', 'SRS Changes Requested'], ['srs_approved', 'SRS Approved'], ['implementation', 'Implementation'], ['final_evaluation', 'Final Evaluation'], ['completed', 'Completed']]
const FILTER_LABEL = { ou_id: 'OU', domain_id: 'Domain', batch_id: 'Batch', stage: 'Stage', week: 'Week', status: 'Review status' }
const REVIEW_STATUS = [['pending', 'Pending'], ['draft', 'In progress'], ['reopened', 'Under revision'], ['submitted', 'Submitted']]

/** Pick a report, narrow it with filters, preview it, and export the complete (scoped) result as CSV or Excel. */
export default function ReportsPage({ title = 'Reports' }) {
  const { user } = useAuth()
  const [reports, setReports] = useState(null)
  const [type, setType] = useState('')
  const [filters, setFilters] = useState({})
  const [page, setPage] = useState(1)
  const [report, setReport] = useState(null)
  const [options, setOptions] = useState({ ou_id: [], domain_id: [], batch_id: [] })
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState('')
  const [detailBatch, setDetailBatch] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    reportService.list().then((list) => { setReports(list); if (list[0]) setType(list[0].type) }).catch((e) => setError(errorMessage(e)))
    batchService.list({ per_page: 100 }).then((r) => setOptions((o) => ({ ...o, batch_id: r.items.map((b) => ({ value: b.id, label: `${b.code} – ${b.name}` })) }))).catch(() => {})
    if (user.role !== 'mentor') {
      domainService.list().then((r) => setOptions((o) => ({ ...o, domain_id: r.map((d) => ({ value: d.id, label: d.name })) }))).catch(() => {})
      ouService.list().then((r) => setOptions((o) => ({ ...o, ou_id: r.map((x) => ({ value: x.id, label: x.name })) }))).catch(() => {})
    }
  }, [user.role])

  const current = reports?.find((r) => r.type === type)
  const params = Object.fromEntries(Object.entries(filters).filter(([k, v]) => v !== '' && current?.filters.includes(k)))
  const key = JSON.stringify([type, params, page])

  useEffect(() => {
    if (!type) return undefined
    let live = true
    setLoading(true); setError('')
    reportService.get(type, { ...params, page, per_page: 25 })
      .then((r) => live && setReport(r)).catch((e) => live && setError(errorMessage(e))).finally(() => live && setLoading(false))
    return () => { live = false }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  const exportAs = async (format) => {
    setExporting(format); setError('')
    try { await reportService.download(type, format, params) } catch (e) { setError(errorMessage(e, 'Export failed')) } finally { setExporting('') }
  }
  const downloadDetailed = async (format, sheet) => {
    setExporting(`detail-${format}-${sheet || ''}`); setError('')
    try { await reportService.batchDetailed(detailBatch, format, sheet) } catch (e) { setError(errorMessage(e, 'Download failed')) } finally { setExporting('') }
  }
  const setFilter = (k) => (e) => { setFilters({ ...filters, [k]: e.target.value }); setPage(1) }

  if (!reports) return error ? <Alert>{error}</Alert> : <Spinner />

  const select = (k, items, empty) => (
    <select key={k} className="input !w-auto" aria-label={`Filter by ${FILTER_LABEL[k]}`} value={filters[k] || ''} onChange={setFilter(k)}>
      <option value="">{empty}</option>{items.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  )

  return (
    <div className="space-y-4">
      <PageHeader title={title} subtitle="Preview a report, then export the full result. Reports only contain data you are allowed to see."
        actions={<>
          <button className="btn-secondary" disabled={!type || Boolean(exporting)} onClick={() => exportAs('csv')}><Download className="h-4 w-4" />{exporting === 'csv' ? 'Exporting…' : 'Export CSV'}</button>
          <button className="btn-primary" disabled={!type || Boolean(exporting)} onClick={() => exportAs('xlsx')}><Download className="h-4 w-4" />{exporting === 'xlsx' ? 'Exporting…' : 'Export Excel'}</button>
        </>} />
      {user.role !== 'mentor' && (
        <section className="card space-y-3" aria-label="Batch detailed report">
          <div className="flex items-start gap-3">
            <FileSpreadsheet className="mt-0.5 h-6 w-6 text-accent" aria-hidden />
            <div>
              <h2 className="font-semibold text-slate-900">Batch detailed report</h2>
              <p className="text-sm text-slate-500">One Excel workbook per batch: summary, every student&apos;s project status, each weekly score with the mentor&apos;s remarks (including each student&apos;s own remark) and the per-criterion marks.</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <select className="input !w-auto" aria-label="Batch for detailed report" value={detailBatch} onChange={(e) => setDetailBatch(e.target.value)}>
              <option value="">Select a batch…</option>{options.batch_id.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <button className="btn-primary" disabled={!detailBatch || Boolean(exporting)} onClick={() => downloadDetailed('xlsx')}>
              <Download className="h-4 w-4" />{exporting.startsWith('detail-xlsx') ? 'Preparing…' : 'Download Excel (all sheets)'}
            </button>
            {[['students', 'Students'], ['weekly', 'Weekly scores'], ['criteria', 'Criteria']].map(([sheet, label]) => (
              <button key={sheet} className="btn-secondary" disabled={!detailBatch || Boolean(exporting)} onClick={() => downloadDetailed('csv', sheet)}>CSV · {label}</button>
            ))}
          </div>
        </section>
      )}
      <div role="tablist" className="flex flex-wrap gap-2">
        {reports.map((r) => (
          <button key={r.type} role="tab" aria-selected={r.type === type} onClick={() => { setType(r.type); setFilters({}); setPage(1); setReport(null) }}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${r.type === type ? 'bg-brand text-white' : 'bg-white text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50'}`}>{r.title.replace(' report', '')}</button>
        ))}
      </div>
      <div className="card space-y-3">
        <div className="flex flex-wrap gap-3">
          {current?.filters.includes('ou_id') && options.ou_id.length > 0 && select('ou_id', options.ou_id.map((o) => [o.value, o.label]), 'All OUs')}
          {current?.filters.includes('domain_id') && options.domain_id.length > 0 && select('domain_id', options.domain_id.map((o) => [o.value, o.label]), 'All domains')}
          {current?.filters.includes('batch_id') && select('batch_id', options.batch_id.map((o) => [o.value, o.label]), 'All batches')}
          {current?.filters.includes('stage') && select('stage', STAGES, 'Any stage')}
          {current?.filters.includes('week') && select('week', [1, 2, 3, 4].map((w) => [w, `Week ${w}`]), 'All weeks')}
          {current?.filters.includes('status') && select('status', REVIEW_STATUS, 'Any status')}
        </div>
        <Alert>{error}</Alert>
        {loading || !report ? <Spinner /> : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm" aria-label={report.title}>
                <thead className="border-b border-slate-200 text-xs uppercase text-slate-500"><tr>{report.columns.map((c) => <th key={c.key} className="whitespace-nowrap px-3 py-2 font-medium">{c.label}</th>)}</tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {report.rows.length === 0 && <tr><td colSpan={report.columns.length} className="px-3 py-8 text-center text-slate-500">No data for these filters.</td></tr>}
                  {report.rows.map((r, i) => <tr key={i} className="hover:bg-slate-50">{report.columns.map((c) => <td key={c.key} className="whitespace-nowrap px-3 py-2">{r[c.key] ?? '—'}</td>)}</tr>)}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-slate-500">{report.meta.total} row(s) · generated {new Date(`${report.generated_at}Z`).toLocaleString()}</p>
            <Pagination meta={report.meta} onPage={setPage} />
          </>
        )}
      </div>
    </div>
  )
}
