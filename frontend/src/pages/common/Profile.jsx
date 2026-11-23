import { useAuth } from '../../context/AuthContext'
import { ROLE_LABEL } from '../../utils/roles'

export default function Profile() {
  const { user } = useAuth()
  const rows = [
    ['Name', user.name],
    ['Email', user.email],
    ['Phone', user.phone || '—'],
    ['Role', ROLE_LABEL[user.role]],
    ['Last login', user.last_login_at ? new Date(user.last_login_at + 'Z').toLocaleString() : '—'],
  ]
  return (
    <div className="max-w-xl space-y-4">
      <h1 className="text-xl font-semibold text-slate-900">My Profile</h1>
      <div className="card">
        <dl className="divide-y divide-slate-100">
          {rows.map(([k, v]) => (
            <div key={k} className="flex justify-between py-2 text-sm">
              <dt className="text-slate-500">{k}</dt>
              <dd className="font-medium text-slate-900">{v}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  )
}
