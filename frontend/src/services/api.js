import axios from 'axios'

const TOKEN_KEY = 'plms_access'
const REFRESH_KEY = 'plms_refresh'

export const tokenStore = {
  get access() { return localStorage.getItem(TOKEN_KEY) },
  get refresh() { return localStorage.getItem(REFRESH_KEY) },
  set({ access_token, refresh_token }) {
    if (access_token) localStorage.setItem(TOKEN_KEY, access_token)
    if (refresh_token) localStorage.setItem(REFRESH_KEY, refresh_token)
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

const api = axios.create({ baseURL: '/api', timeout: 30000 })

api.interceptors.request.use((config) => {
  const token = tokenStore.access
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

let refreshing = null

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config
    const status = error.response?.status
    const isAuthCall = original?.url?.startsWith('/auth/login') || original?.url?.startsWith('/auth/refresh')
    if (status === 401 && !original._retried && !isAuthCall && tokenStore.refresh) {
      original._retried = true
      try {
        refreshing = refreshing || axios.post('/api/auth/refresh', null, {
          headers: { Authorization: `Bearer ${tokenStore.refresh}` },
        })
        const { data } = await refreshing
        tokenStore.set({ access_token: data.data.access_token })
        original.headers.Authorization = `Bearer ${data.data.access_token}`
        return api(original)
      } catch {
        tokenStore.clear()
        window.dispatchEvent(new Event('plms:logout'))
      } finally {
        refreshing = null
      }
    } else if (status === 401 && !isAuthCall) {
      tokenStore.clear()
      window.dispatchEvent(new Event('plms:logout'))
    }
    return Promise.reject(error)
  },
)

/** Turn any axios error into a readable message (uses the backend's envelope when present). */
export function errorMessage(err, fallback = 'Something went wrong. Please try again.') {
  const body = err?.response?.data
  if (body?.message === 'Validation failed' && body.errors && typeof body.errors === 'object') {
    const first = Object.values(body.errors).flat()[0]
    if (typeof first === 'string') return `Validation failed: ${first}`
  }
  return body?.message || (err?.request && !err?.response ? 'Cannot reach the server.' : fallback)
}

/** Field-level validation messages from the backend: { fieldName: 'message' }. */
export function fieldErrors(err) {
  const e = err?.response?.data?.errors
  if (!e || typeof e !== 'object') return {}
  return Object.fromEntries(Object.entries(e).map(([k, v]) => [k, Array.isArray(v) ? v[0] : String(v)]))
}

export default api
