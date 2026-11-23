export default function Pagination({ meta, onPage }) {
  if (!meta || meta.pages <= 1) return null
  return (
    <div className="flex items-center justify-between pt-3 text-sm text-slate-600">
      <span>Page {meta.page} of {meta.pages} · {meta.total} records</span>
      <div className="flex gap-2">
        <button className="btn-secondary" disabled={meta.page <= 1} onClick={() => onPage(meta.page - 1)}>Previous</button>
        <button className="btn-secondary" disabled={meta.page >= meta.pages} onClick={() => onPage(meta.page + 1)}>Next</button>
      </div>
    </div>
  )
}
