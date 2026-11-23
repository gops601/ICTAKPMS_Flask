import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { notificationService } from '../../services/adminService'
import { useList } from '../../hooks/useList'
import { timeAgo } from '../../components/NotificationBell'
import PageHeader from '../../components/PageHeader'
import Pagination from '../../components/Pagination'
import Spinner from '../../components/Spinner'
import Alert from '../../components/Alert'
import { EmptyState } from '../../components/illustrations'

export default function Notifications() {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [unread, setUnread] = useState(false)
  const { items, meta, loading, error, reload } = useList(notificationService.list, { page, unread: unread ? 1 : undefined })

  const open = async (n) => {
    if (!n.is_read) await notificationService.markRead(n.id).catch(() => {})
    if (n.link) navigate(n.link)
    else reload()
  }
  const readAll = async () => { await notificationService.readAll(); reload() }

  return (
    <div className="max-w-3xl">
      <PageHeader title="Notifications" actions={<>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={unread} onChange={(e) => { setUnread(e.target.checked); setPage(1) }} />Unread only</label>
        <button className="btn-secondary" onClick={readAll}>Mark all as read</button>
      </>} />
      <Alert>{error}</Alert>
      <div className="card p-0">
        {loading ? <Spinner /> : (
          <ul className="divide-y divide-slate-100">
            {items.length === 0 && <li><EmptyState title="No notifications." /></li>}
            {items.map((n) => (
              <li key={n.id}>
                <button onClick={() => open(n)} className={`flex w-full items-start gap-3 px-5 py-3 text-left hover:bg-slate-50 ${n.is_read ? '' : 'bg-rose-50/60'}`}>
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${n.is_read ? 'bg-transparent' : 'bg-brand'}`} aria-label={n.is_read ? 'read' : 'unread'} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-medium text-slate-900">{n.title}</span>
                    {n.message && <span className="block text-sm text-slate-600">{n.message}</span>}
                  </span>
                  <span className="shrink-0 text-xs text-slate-400">{timeAgo(n.created_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <Pagination meta={meta} onPage={setPage} />
    </div>
  )
}
