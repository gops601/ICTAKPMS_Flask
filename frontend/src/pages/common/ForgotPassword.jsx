import { useState } from 'react'
import { Link } from 'react-router-dom'
import AuthLayout from '../../layouts/AuthLayout'
import Alert from '../../components/Alert'
import { authService } from '../../services/authService'
import { errorMessage } from '../../services/api'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      await authService.forgotPassword(email)
      setDone(true)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthLayout title="Forgot password" subtitle="Enter your email and we will send a reset link.">
      {done ? (
        <div className="space-y-4">
          <Alert type="success">If an account exists for that email, a reset link has been sent.</Alert>
          <Link to="/login" className="btn-secondary w-full">Back to sign in</Link>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <Alert>{error}</Alert>
          <div>
            <label htmlFor="email" className="label">Email</label>
            <input id="email" type="email" required className="input" value={email}
              onChange={(e) => setEmail(e.target.value)} />
          </div>
          <button type="submit" className="btn-primary w-full" disabled={busy}>
            {busy ? 'Sending…' : 'Send reset link'}
          </button>
          <div className="text-center text-sm">
            <Link to="/login" className="text-brand hover:underline">Back to sign in</Link>
          </div>
        </form>
      )}
    </AuthLayout>
  )
}
