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
        sans: ['-apple-system', 'BlinkMacSystemFont', '"SF Pro Text"', '"Segoe UI Variable Text"', '"Segoe UI"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        // iOS dark labels
        ink: { DEFAULT: '#ffffff', muted: 'rgba(235,235,245,0.6)', faint: 'rgba(235,235,245,0.3)' },
        ios: {
          bg: '#000000', cell: '#1c1c1e', raised: '#2c2c2e', fill: 'rgba(118,118,128,0.24)',
          blue: '#0a84ff', green: '#30d158', red: '#ff453a', orange: '#ff9f0a', yellow: '#ffd60a',
          indigo: '#5e5ce6', purple: '#bf5af2', teal: '#64d2ff',
        },
        signal: { critical: '#ff453a', warning: '#ff9f0a', clear: '#30d158', info: '#0a84ff' },
        // old brand names now point at iOS colors so existing classes follow the new look
        gs: { blue: '#0a84ff', gold: '#0a84ff', dark: '#000000', card: '#1c1c1e' },
      },
    },
  },
  plugins: [],
}
