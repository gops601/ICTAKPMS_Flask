import { useState } from 'react'
import Alert from '../../components/Alert'
import { useAuth } from '../../context/AuthContext'
import { authService } from '../../services/authService'
import { errorMessage } from '../../services/api'

export default function ChangePassword() {
  const { user, refreshUser } = useAuth()
  const [form, setForm] = useState({ current: '', next: '', confirm: '' })
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setSuccess('')
    if (form.next !== form.confirm) return setError('New passwords do not match')
    setBusy(true)
    try {
      await authService.changePassword(form.current, form.next)
      setSuccess('Password changed successfully.')
      setForm({ current: '', next: '', confirm: '' })
      await refreshUser()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-md space-y-4">
      <h1 className="text-xl font-semibold text-slate-900">Change Password</h1>
      {user.must_change_password && <Alert type="warning">You must change your temporary password before continuing.</Alert>}
      <form onSubmit={submit} className="card space-y-4">
        <Alert>{error}</Alert>
        <Alert type="success">{success}</Alert>
        <div>
          <label htmlFor="cur" className="label">Current password</label>
          <input id="cur" type="password" required className="input" value={form.current} onChange={set('current')} autoComplete="current-password" />
        </div>
        <div>
          <label htmlFor="new" className="label">New password</label>
          <input id="new" type="password" required minLength={8} className="input" value={form.next} onChange={set('next')} autoComplete="new-password" />
        </div>
        <div>
          <label htmlFor="conf" className="label">Confirm new password</label>
          <input id="conf" type="password" required className="input" value={form.confirm} onChange={set('confirm')} autoComplete="new-password" />
        </div>
        <button type="submit" className="btn-primary" disabled={busy}>{busy ? 'Saving…' : 'Update password'}</button>
      </form>
    </div>
  )
}
