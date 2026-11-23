import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Bell } from 'lucide-react'
import { notificationService } from '../services/adminService'

const POLL_MS = 60000

export const timeAgo = (iso) => {
  const secs = Math.max(0, (Date.now() - new Date(`${iso}Z`).getTime()) / 1000)
  if (secs < 60) return 'just now'
  if (secs < 3600) return `${Math.floor(secs / 60)} min ago`
  if (secs < 86400) return `${Math.floor(secs / 3600)} h ago`
  return `${Math.floor(secs / 86400)} d ago`
}

/** Bell with live unread count (polled) and a dropdown of the latest notifications. */
export default function NotificationBell() {
  const navigate = useNavigate()
  const [count, setCount] = useState(0)
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState([])
  const box = useRef(null)

  const refreshCount = useCallback(() => notificationService.unreadCount().then(setCount).catch(() => {}), [])

  useEffect(() => {
    refreshCount()
    const t = setInterval(refreshCount, POLL_MS)
    return () => clearInterval(t)
  }, [refreshCount])

  useEffect(() => {
    const close = (e) => box.current && !box.current.contains(e.target) && setOpen(false)
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const toggle = async () => {
    const next = !open
    setOpen(next)
    if (next) {
      try { setItems((await notificationService.list({ per_page: 8 })).items) } catch { setItems([]) }
    }
  }

  const openItem = async (n) => {
    setOpen(false)
    if (!n.is_read) { await notificationService.markRead(n.id).catch(() => {}); refreshCount() }
    if (n.link) navigate(n.link)
  }

  const readAll = async () => {
    await notificationService.readAll().catch(() => {})
    setItems((list) => list.map((n) => ({ ...n, is_read: true })))
    setCount(0)
  }

  return (
    <div className="relative" ref={box}>
      <button onClick={toggle} aria-label={`Notifications${count ? `, ${count} unread` : ''}`} className="relative rounded-lg p-2 text-slate-600 hover:bg-slate-100">
        <Bell className="h-5 w-5" />
        {count > 0 && (
          <span data-testid="unread-badge" className="absolute -right-0.5 -top-0.5 min-w-[18px] rounded-full bg-red-600 px-1 text-center text-[11px] font-semibold leading-[18px] text-white">
            {count > 99 ? '99+' : count}
          </span>
        )}
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-40 mt-2 w-80 rounded-xl bg-white shadow-lg ring-1 ring-slate-200">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2">
            <span className="text-sm font-semibold">Notifications</span>
            {count > 0 && <button className="text-xs text-brand hover:underline" onClick={readAll}>Mark all read</button>}
          </div>
          <ul className="max-h-80 divide-y divide-slate-100 overflow-y-auto">
            {items.length === 0 && <li className="px-4 py-6 text-center text-sm text-slate-500">You're all caught up.</li>}
            {items.map((n) => (
              <li key={n.id}>
                <button role="menuitem" onClick={() => openItem(n)} className={`w-full px-4 py-2.5 text-left hover:bg-slate-50 ${n.is_read ? '' : 'bg-blue-50/60'}`}>
                  <div className="text-sm font-medium text-slate-900">{n.title}</div>
                  {n.message && <div className="line-clamp-2 text-xs text-slate-600">{n.message}</div>}
                  <div className="mt-0.5 text-[11px] text-slate-400">{timeAgo(n.created_at)}</div>
                </button>
              </li>
            ))}
          </ul>
          <Link to="/notifications" onClick={() => setOpen(false)} className="block border-t border-slate-100 px-4 py-2 text-center text-sm text-brand hover:bg-slate-50">View all</Link>
        </div>
      )}
    </div>
  )
}
