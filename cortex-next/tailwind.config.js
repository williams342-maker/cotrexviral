/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['ui-sans-serif', 'system-ui', '-apple-system', 'Inter', 'sans-serif'],
        display: ['"Cabinet Grotesk"', 'ui-sans-serif', 'system-ui'],
      },
      colors: {
        cortex: {
          bg: '#09090B',
          card: '#101013',
          violet: '#7C3AED',
          cyan: '#22D3EE',
        },
      },
    },
  },
  plugins: [],
};
