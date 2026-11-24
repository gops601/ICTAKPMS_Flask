import { useEffect, useState } from 'react'
import { batchMentorService, userService } from '../services/adminService'
import { errorMessage } from '../services/api'
import Modal from './Modal'
import Alert from './Alert'

/**
 * Add one or several mentors to a batch. They then see the batch, its students and the projects students propose
 * (which they approve from Proposal Approvals). Offers the batch's domain mentors who are not on it yet.
 */
export default function AddBatchMentorsModal({ batch, onClose, onDone }) {
  const [pool, setPool] = useState(null)
  const [picked, setPicked] = useState(new Set())
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    (async () => {
      try {
        const [all, current] = await Promise.all([
          userService.mentors({ per_page: 100, for_domain: batch.domain?.id }),
          batchMentorService.list(batch.id),
        ])
        const on = new Set(current.map((m) => m.id))
        setPool(all.items.filter((m) => m.is_active && !on.has(m.id)))
      } catch (e) { setError(errorMessage(e)); setPool([]) }
    })()
  }, [batch.id, batch.domain?.id])

  const toggle = (id) => setPicked((cur) => { const n = new Set(cur); n.has(id) ? n.delete(id) : n.add(id); return n })
  const shown = (pool || []).filter((m) => !q || `${m.name} ${m.email}`.toLowerCase().includes(q.toLowerCase()))
  const save = async () => {
    setBusy(true); setError('')
    try { await batchMentorService.assignMany(batch.id, [...picked]); onDone() } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }

  return (
    <Modal title={`Add mentors – ${batch.code}`} onClose={onClose}
      footer={<><button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" disabled={busy || picked.size === 0} onClick={save}>{busy ? 'Adding…' : `Add ${picked.size || ''} mentor${picked.size === 1 ? '' : 's'}`.replace('  ', ' ')}</button></>}>
      <div className="space-y-3">
        <Alert>{error}</Alert>
        <input className="input" placeholder="Search mentors…" aria-label="Search mentors" value={q} onChange={(e) => setQ(e.target.value)} />
        {pool === null && <p className="text-sm text-slate-500">Loading mentors…</p>}
        {pool && pool.length === 0 && !error && <p className="text-sm text-slate-500">Every available mentor is already on this batch.</p>}
        <ul className="max-h-72 space-y-1 overflow-y-auto rounded-xl border border-slate-200 p-2">
          {shown.map((m) => (
            <li key={m.id}>
              <label className="flex cursor-pointer items-center gap-3 rounded-lg px-2 py-1.5 text-sm hover:bg-slate-50">
                <input type="checkbox" checked={picked.has(m.id)} onChange={() => toggle(m.id)} />
                <span className="font-medium">{m.name}</span><span className="text-slate-500">{m.email}</span>
                <span className="ml-auto text-xs text-slate-400">{m.project_count ?? 0} projects</span>
              </label>
            </li>
          ))}
        </ul>
        <p className="text-xs text-slate-500">Added mentors can allocate projects in this batch and approve the projects its students propose.</p>
      </div>
    </Modal>
  )
}
