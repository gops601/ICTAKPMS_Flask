/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // "Forest & gold": deep green sidebar, emerald primary and warm amber accent on a soft stone canvas.
        navy: { 950: '#04201a', 900: '#0a2f27', 800: '#0f3d33', 700: '#14532d' },
        brand: { DEFAULT: '#047857', dark: '#065f46', light: '#d1fae5' },
        accent: { DEFAULT: '#d97706', dark: '#b45309', light: '#fef3c7' },
        canvas: '#f5f7f4',
      },
      boxShadow: {
        soft: '0 1px 2px rgba(4,32,26,0.05), 0 8px 24px -12px rgba(4,32,26,0.18)',
      },
      fontFamily: { sans: ['Inter', 'system-ui', '-apple-system', '"Segoe UI"', 'Roboto', 'sans-serif'] },
    },
  },
  plugins: [],
}
