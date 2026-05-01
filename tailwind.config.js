/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{svelte,js,ts}'
  ],
  theme: {
    extend: {
      colors: {
        ink: '#15171a',
        panel: '#f7f8fb',
        line: '#dce1ea',
        muted: '#687386'
      },
      boxShadow: {
        tile: '0 8px 24px rgba(23, 28, 38, 0.08)'
      }
    }
  },
  plugins: []
}
