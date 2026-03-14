import type { Config } from 'tailwindcss';
import forms from '@tailwindcss/forms';

export default {
  content: ['./src/**/*.{html,js,svelte,ts}'],
  theme: {
    extend: {
      colors: {
        border: 'hsl(240 5.9% 90%)',
        input: 'hsl(240 5.9% 90%)',
        ring: 'hsl(240 5% 64.9%)',
        background: 'hsl(0 0% 100%)',
        foreground: 'hsl(240 10% 3.9%)',
        primary: {
          DEFAULT: 'hsl(240 5.9% 10%)',
          foreground: 'hsl(0 0% 98%)'
        },
        secondary: {
          DEFAULT: 'hsl(240 4.8% 95.9%)',
          foreground: 'hsl(240 5.9% 10%)'
        },
        muted: {
          DEFAULT: 'hsl(240 4.8% 95.9%)',
          foreground: 'hsl(240 3.8% 46.1%)'
        },
        accent: {
          DEFAULT: 'hsl(240 4.8% 95.9%)',
          foreground: 'hsl(240 5.9% 10%)'
        },
        destructive: {
          DEFAULT: 'hsl(0 84.2% 60.2%)',
          foreground: 'hsl(0 0% 98%)'
        }
      },
      borderRadius: {
        lg: '0.75rem',
        md: '0.5rem',
        sm: '0.375rem'
      },
      boxShadow: {
        card: '0 1px 2px 0 rgb(0 0 0 / 0.05), 0 1px 3px 1px rgb(0 0 0 / 0.03)'
      }
    }
  },
  plugins: [forms]
} satisfies Config;

