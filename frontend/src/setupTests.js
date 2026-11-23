import '@testing-library/jest-dom/vitest'

// Newer Node versions expose an experimental global `localStorage` that can shadow jsdom's
// implementation; install a deterministic in-memory Storage for tests.
class MemoryStorage {
  #m = new Map()
  get length() { return this.#m.size }
  key(i) { return [...this.#m.keys()][i] ?? null }
  getItem(k) { return this.#m.has(String(k)) ? this.#m.get(String(k)) : null }
  setItem(k, v) { this.#m.set(String(k), String(v)) }
  removeItem(k) { this.#m.delete(String(k)) }
  clear() { this.#m.clear() }
}
Object.defineProperty(globalThis, 'localStorage', { value: new MemoryStorage(), configurable: true })
Object.defineProperty(window, 'localStorage', { value: globalThis.localStorage, configurable: true })

window.scrollTo = () => {}

// jsdom has no layout engine: Recharts' ResponsiveContainer needs ResizeObserver to mount.
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
}
