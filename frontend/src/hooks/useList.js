import { useCallback, useEffect, useRef, useState } from 'react'
import { errorMessage } from '../services/api'

/** Debounce a fast-changing value (search boxes). */
export function useDebounced(value, delay = 350) {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return v
}

/**
 * Loads a paginated/filterable list. `fetcher(params)` must resolve to { items, meta }.
 * Ignores stale responses so fast filter changes never show out-of-order data.
 */
export function useList(fetcher, params) {
  const [state, setState] = useState({ items: [], meta: null, loading: true, error: '' })
  const seq = useRef(0)
  const key = JSON.stringify(params)

  const load = useCallback(async () => {
    const id = ++seq.current
    setState((s) => ({ ...s, loading: true, error: '' }))
    try {
      const res = await fetcher(JSON.parse(key))
      if (id === seq.current) setState({ items: res.items, meta: res.meta, loading: false, error: '' })
    } catch (e) {
      if (id === seq.current) setState((s) => ({ ...s, loading: false, error: errorMessage(e) }))
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  useEffect(() => { load() }, [load])
  return { ...state, reload: load }
}
