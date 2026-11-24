/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // ICTAK teal: the logo's blue-green as the primary, deep teal for dark surfaces, a soft cool canvas and a warm amber accent.
        navy: { 950: '#04222c', 900: '#06303d', 800: '#0a4254', 700: '#0e566c' },
        brand: { DEFAULT: '#0a819f', dark: '#066782', light: '#d6eef4' },
        accent: { DEFAULT: '#d97706', dark: '#b45309', light: '#fef3c7' },
        // Tailwind's rose scale is re-pointed at the logo teal, so existing rose-* classes follow the brand.
        rose: { 50: '#eef8fb', 100: '#d6eef4', 200: '#aedde8', 300: '#7cc6d8', 400: '#3fa6c0', 500: '#0e8cab', 600: '#0a7a97', 700: '#066782', 800: '#07546a', 900: '#073f50' },
        canvas: '#e8f3f6',
      },
      boxShadow: {
        soft: '0 1px 2px rgba(4,34,44,0.05), 0 8px 24px -12px rgba(4,34,44,0.18)',
      },
      fontFamily: { sans: ['Inter', 'system-ui', '-apple-system', '"Segoe UI"', 'Roboto', 'sans-serif'] },
    },
  },
  plugins: [],
}
