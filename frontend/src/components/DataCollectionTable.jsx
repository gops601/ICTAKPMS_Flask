/** Read-only view of the detailed data-collection sheet a student filled in (one card per dataset). */
const FIELDS = [
  ['source', 'Source'], ['data_type', 'Data type'], ['file_format', 'Format'], ['records', 'Records'], ['features', 'Features'],
  ['collection_method', 'Collected by'], ['collection_period', 'Period'], ['license', 'License'], ['personal_data', 'Personal data'],
]

export default function DataCollectionTable({ rows, title = 'Data collection' }) {
  if (!rows || rows.length === 0) return null
  return (
    <section className="card" aria-label={title}>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h2>
      <div className="space-y-3">
        {rows.map((r, i) => (
          <div key={i} className="rounded-lg border border-slate-200 p-3 text-sm">
            <div className="font-medium text-slate-900">{r.name}</div>
            <p className="text-slate-600">{r.description}</p>
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-3">
              {FIELDS.filter(([k]) => r[k] !== null && r[k] !== undefined && r[k] !== '').map(([k, l]) => (
                <div key={k}><dt className="inline text-slate-500">{l}: </dt><dd className="inline font-medium text-slate-800">{String(r[k])}</dd></div>
              ))}
            </dl>
            {r.feature_names && <p className="mt-1 text-xs text-slate-600"><span className="text-slate-500">Columns:</span> {r.feature_names}{r.target ? ` · target: ${r.target}` : ''}</p>}
            {r.source_url && <p className="text-xs text-slate-600"><span className="text-slate-500">URL:</span> {r.source_url}</p>}
            {r.privacy && <p className="text-xs text-slate-600"><span className="text-slate-500">Privacy:</span> {r.privacy}</p>}
            {r.limitations && <p className="text-xs text-slate-600"><span className="text-slate-500">Limitations:</span> {r.limitations}</p>}
          </div>
        ))}
      </div>
    </section>
  )
}
