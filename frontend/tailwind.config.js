/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Schibsted Grotesk"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        ink: { DEFAULT: '#e6ecf5', muted: '#8a97ad' },
        signal: { critical: '#ff5a5f', warning: '#f5b83d', clear: '#3dd6a0', info: '#5aa9ff' },
        gs: {
          blue: '#1b365d',
          gold: '#c9a45c',
          dark: '#0a1628',
          card: '#1e293b'
        }
      }
    },
  },
  plugins: [],
}
