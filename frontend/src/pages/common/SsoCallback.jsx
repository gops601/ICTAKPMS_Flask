import { useEffect, useState } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import api, { errorMessage, tokenStore } from '../../services/api'
import { useAuth } from '../../context/AuthContext'
import { ROLE_HOME } from '../../utils/roles'
import AuthLayout from '../../layouts/AuthLayout'
import Alert from '../../components/Alert'
import Spinner from '../../components/Spinner'

/** Landing page for "sign in from another portal": /sso?portal=<slug>&token=<signed token>. */
export default function SsoCallback() {
  const [params] = useSearchParams()
  const { refreshUser } = useAuth()
  const [error, setError] = useState('')
  const [role, setRole] = useState(null)

  useEffect(() => {
    const portal = params.get('portal'), token = params.get('token')
    if (!portal || !token) { setError('This sign-in link is incomplete.'); return }
    api.post('/auth/sso', { portal, token })
      .then(async (r) => { tokenStore.set(r.data.data); await refreshUser(); setRole(r.data.data.user.role) })
      .catch((e) => setError(errorMessage(e, 'Single sign-on failed.')))
  }, [params, refreshUser])

  if (role) return <Navigate to={ROLE_HOME[role]} replace />
  return (
    <AuthLayout title="Signing you in…" subtitle="Using your account from the other portal.">
      {error ? <><Alert>{error}</Alert><a className="mt-3 inline-block text-sm text-brand hover:underline" href="/login">Go to the sign-in page</a></> : <Spinner />}
    </AuthLayout>
  )
}
