import { useEffect, useState } from 'react'
import { batchService } from '../services/adminService'

/**
 * Batch selector for admins, Domain Leads and mentors. The list comes from the API, which already limits it
 * to the batches the signed-in user may access. `value` is '' for "all batches".
 */
export default function BatchFilter({ value, onChange, label = 'Batch', className = '' }) {
  const [batches, setBatches] = useState([])
  useEffect(() => {
    batchService.list({ per_page: 100, sort: 'code', order: 'asc' }).then((r) => setBatches(Array.isArray(r?.items) ? r.items : [])).catch(() => setBatches([]))
  }, [])
  return (
    <select className={`input !w-auto ${className}`} aria-label={`Filter by ${label.toLowerCase()}`} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">All batches</option>
      {batches.map((b) => <option key={b.id} value={b.id}>{b.code} – {b.name}</option>)}
    </select>
  )
}
