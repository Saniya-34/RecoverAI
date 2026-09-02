/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: '#3f3fe8',
          dark:    '#3232c4',
          light:   '#eef0ff',
          mid:     '#c5caf8',
        },
        amber: {
          DEFAULT: '#c96c00',
          bg:      '#fff7ed',
          border:  '#fed7aa',
        },
        success: {
          DEFAULT: '#15803d',
          bg:      '#f0fdf4',
          border:  '#bbf7d0',
        },
        danger: {
          DEFAULT: '#b91c1c',
          bg:      '#fef2f2',
          border:  '#fecaca',
        },
        sky: {
          DEFAULT: '#0369a1',
          bg:      '#f0f9ff',
          border:  '#bae6fd',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['ui-monospace', 'SF Mono', 'Consolas', 'monospace'],
      },
      fontSize: {
        '2xs': '10px',
        xs:    '11px',
        sm:    '12px',
        base:  '14px',
        md:    '15px',
        lg:    '17px',
        xl:    '20px',
        '2xl': '24px',
        '3xl': '28px',
        '4xl': '32px',
      },
      boxShadow: {
        xs: '0 1px 2px rgba(0,0,0,0.05)',
        sm: '0 1px 4px rgba(0,0,0,0.07), 0 1px 2px rgba(0,0,0,0.04)',
        md: '0 4px 8px rgba(0,0,0,0.07), 0 2px 4px rgba(0,0,0,0.04)',
      },
      borderRadius: {
        DEFAULT: '8px',
        sm: '4px',
        md: '8px',
        lg: '12px',
        xl: '16px',
      },
    },
  },
  plugins: [],
}
