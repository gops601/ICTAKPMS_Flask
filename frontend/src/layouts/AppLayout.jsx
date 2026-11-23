import { useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { LogOut, Menu, X } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import NotificationBell from '../components/NotificationBell'
import { LogoMark } from '../components/illustrations'
import { APP_NAME } from '../utils/brand'
import { COMMON_MENU, ROLE_LABEL, ROLE_MENU } from '../utils/roles'

function NavItem({ item, onClick }) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onClick}
      className={({ isActive }) =>
        `flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition ${
          isActive ? 'bg-white/15 text-white shadow-inner ring-1 ring-white/10' : 'text-emerald-100/80 hover:bg-white/10 hover:text-white'
        }`
      }
    >
      <Icon className="h-4 w-4" aria-hidden />
      {item.label}
    </NavLink>
  )
}

function Breadcrumbs() {
  const { pathname } = useLocation()
  const parts = pathname.split('/').filter(Boolean)
  return (
    <nav aria-label="Breadcrumb" className="text-sm text-slate-500">
      {parts.map((p, i) => (
        <span key={i}>
          {i > 0 && <span className="mx-1">/</span>}
          <span className={i === parts.length - 1 ? 'font-medium text-slate-800' : ''}>
            {p.replace(/-/g, ' ').replace(/^\w/, (c) => c.toUpperCase())}
          </span>
        </span>
      ))}
    </nav>
  )
}

export default function AppLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const menu = ROLE_MENU[user.role] || []

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  const sidebar = (
    <div className="flex h-full flex-col bg-gradient-to-b from-navy-900 via-navy-900 to-navy-800 p-4">
      <div className="mb-6 flex items-center gap-3 px-2">
        <LogoMark size={38} />
        <div>
          <div className="text-lg font-bold leading-tight text-white">{APP_NAME}</div>
          <div className="text-xs text-amber-300">{ROLE_LABEL[user.role]}</div>
        </div>
      </div>
      <nav aria-label="Main navigation" className="flex-1 space-y-1 overflow-y-auto pr-1">
        {menu.map((m) => <NavItem key={m.to} item={m} onClick={() => setOpen(false)} />)}
        <div className="my-3 border-t border-white/10" />
        {COMMON_MENU.map((m) => <NavItem key={m.to} item={m} onClick={() => setOpen(false)} />)}
      </nav>
    </div>
  )

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 md:block">{sidebar}</aside>
      {open && (
        <div className="fixed inset-0 z-40 flex md:hidden">
          <div className="w-64">{sidebar}</div>
          <button className="flex-1 bg-black/40" aria-label="Close menu" onClick={() => setOpen(false)} />
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-slate-200/70 bg-white/85 px-4 backdrop-blur">
          <div className="flex items-center gap-3">
            <button className="md:hidden" aria-label="Open menu" onClick={() => setOpen(!open)}>
              {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
            <Breadcrumbs />
          </div>
          <div className="flex items-center gap-4">
            <NotificationBell />
            <div className="hidden text-right sm:block">
              <div className="text-sm font-semibold text-slate-900">{user.name}</div>
              <div className="text-xs text-slate-500">{user.email}</div>
            </div>
            <button className="btn-secondary" onClick={handleLogout}>
              <LogOut className="h-4 w-4" aria-hidden /> Logout
            </button>
          </div>
        </header>
        <main className="flex-1 p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
