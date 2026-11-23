import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import AuthLayout from '../../layouts/AuthLayout'
import Alert from '../../components/Alert'
import { authService } from '../../services/authService'
import { errorMessage } from '../../services/api'

export default function ResetPassword() {
  const { token } = useParams()
  const navigate = useNavigate()
  const [pw, setPw] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    if (pw !== confirm) return setError('Passwords do not match')
    setBusy(true)
    try {
      await authService.resetPassword(token, pw)
      navigate('/login', { replace: true })
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthLayout title="Reset password" subtitle="Choose a new password (8+ characters, letters and numbers).">
      <form onSubmit={submit} className="space-y-4">
        <Alert>{error}</Alert>
        <div>
          <label htmlFor="pw" className="label">New password</label>
          <input id="pw" type="password" required minLength={8} className="input" value={pw}
            onChange={(e) => setPw(e.target.value)} autoComplete="new-password" />
        </div>
        <div>
          <label htmlFor="confirm" className="label">Confirm password</label>
          <input id="confirm" type="password" required className="input" value={confirm}
            onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" />
        </div>
        <button type="submit" className="btn-primary w-full" disabled={busy}>
          {busy ? 'Saving…' : 'Reset password'}
        </button>
        <div className="text-center text-sm">
          <Link to="/login" className="text-brand hover:underline">Back to sign in</Link>
        </div>
      </form>
    </AuthLayout>
  )
}
