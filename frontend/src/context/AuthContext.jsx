import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { tokenStore } from '../services/api'
import { authService } from '../services/authService'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(Boolean(tokenStore.access))

  const logout = useCallback(() => {
    tokenStore.clear()
    setUser(null)
  }, [])

  useEffect(() => {
    window.addEventListener('plms:logout', logout)
    return () => window.removeEventListener('plms:logout', logout)
  }, [logout])

  useEffect(() => {
    if (!tokenStore.access) return
    authService.me().then(setUser).catch(logout).finally(() => setLoading(false))
  }, [logout])

  const login = useCallback(async (email, password) => {
    const data = await authService.login(email, password)
    tokenStore.set(data)
    setUser(data.user)
    return data.user
  }, [])

  const refreshUser = useCallback(() => authService.me().then(setUser), [])

  const value = useMemo(() => ({ user, loading, login, logout, refreshUser }), [user, loading, login, logout, refreshUser])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
