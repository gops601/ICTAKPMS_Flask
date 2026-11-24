/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Light rose & saffron: soft blush surfaces, rose primary and warm amber accent on a beige canvas.
        navy: { 950: '#2a0a12', 900: '#3b0f1b', 800: '#4f1524', 700: '#6b1d31' },
        brand: { DEFAULT: '#e11d48', dark: '#be123c', light: '#ffe4e6' },
        accent: { DEFAULT: '#d97706', dark: '#b45309', light: '#fef3c7' },
        canvas: '#f2e8d5',
      },
      boxShadow: {
        soft: '0 1px 2px rgba(42,10,18,0.05), 0 8px 24px -12px rgba(42,10,18,0.18)',
      },
      fontFamily: { sans: ['Inter', 'system-ui', '-apple-system', '"Segoe UI"', 'Roboto', 'sans-serif'] },
    },
  },
  plugins: [],
}
