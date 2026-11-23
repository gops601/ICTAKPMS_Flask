import { ArrowDown, ArrowUp } from 'lucide-react'
import Spinner from './Spinner'
import { EmptyState } from './illustrations'

/**
 * columns: [{ key, header, render?(row), sortKey? }]; sorting is server-side via onSort(sortKey).
 */
export default function DataTable({ columns, rows, loading, empty = 'No records found.', sort, onSort, rowKey = 'id' }) {
  if (loading) return <Spinner />
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
          <tr>
            {columns.map((c) => (
              <th key={c.key} className="px-3 py-2 font-medium">
                {c.sortKey && onSort ? (
                  <button className="inline-flex items-center gap-1 uppercase" onClick={() => onSort(c.sortKey)}>
                    {c.header}
                    {sort?.key === c.sortKey && (sort.order === 'asc' ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
                  </button>
                ) : c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.length === 0 && (
            <tr><td colSpan={columns.length}><EmptyState title={empty} /></td></tr>
          )}
          {rows.map((r) => (
            <tr key={r[rowKey]} className="hover:bg-slate-50">
              {columns.map((c) => <td key={c.key} className="px-3 py-2.5 align-middle">{c.render ? c.render(r) : r[c.key]}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
