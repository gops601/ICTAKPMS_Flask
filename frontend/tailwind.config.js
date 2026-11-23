/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // "Indigo night" sidebar + vivid indigo primary + teal accent on a soft lavender-grey canvas.
        navy: { 950: '#12102e', 900: '#1b1946', 800: '#25226b', 700: '#312e81' },
        brand: { DEFAULT: '#4f46e5', dark: '#4338ca', light: '#e0e7ff' },
        accent: { DEFAULT: '#0d9488', dark: '#0f766e', light: '#ccfbf1' },
        canvas: '#f4f5fb',
      },
      boxShadow: {
        soft: '0 1px 2px rgba(30,27,75,0.05), 0 8px 24px -12px rgba(30,27,75,0.18)',
      },
      fontFamily: { sans: ['Inter', 'system-ui', '-apple-system', '"Segoe UI"', 'Roboto', 'sans-serif'] },
    },
  },
  plugins: [],
}
