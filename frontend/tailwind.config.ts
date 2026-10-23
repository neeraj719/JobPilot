import type { Config } from 'tailwindcss'
import animate from 'tailwindcss-animate'

/** `hsl(var(--x))` keeps Tailwind's opacity modifiers working (`bg-primary/10`). */
const token = (name: string) => `hsl(var(--${name}))`

/** A semantic status colour: solid (`bg-success`), its text-on-solid, and a soft pair. */
const status = (name: string) => ({
  DEFAULT: token(name),
  foreground: token(`${name}-foreground`),
  soft: token(`${name}-soft`),
  'soft-foreground': token(`${name}-soft-foreground`),
})

/** Tinted, layered shadow; `--shadow-strength` makes it heavier on the dark surfaces. */
const shadow = (layers: [number, number, number, number][]) =>
  layers
    .map(([y, blur, spread, alpha]) => `0 ${y}px ${blur}px ${spread}px hsl(var(--shadow-color) / calc(${alpha} * var(--shadow-strength)))`)
    .join(', ')

const config: Config = {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    container: {
      center: true,
      padding: {
        DEFAULT: '1rem',
        lg: '2rem',
      },
      screens: {
        '2xl': '1440px',
      },
    },
    extend: {
      colors: {
        border: token('border'),
        input: token('input'),
        ring: token('ring'),
        background: token('background'),
        foreground: token('foreground'),
        overlay: token('overlay'),
        primary: {
          DEFAULT: token('primary'),
          foreground: token('primary-foreground'),
        },
        secondary: {
          DEFAULT: token('secondary'),
          foreground: token('secondary-foreground'),
        },
        destructive: status('destructive'),
        success: status('success'),
        warning: status('warning'),
        info: status('info'),
        /** AI-made content (suggestions, tailored text, "AI" version badges). Not a status. */
        ai: status('ai'),
        muted: {
          DEFAULT: token('muted'),
          foreground: token('muted-foreground'),
        },
        accent: {
          DEFAULT: token('accent'),
          foreground: token('accent-foreground'),
        },
        popover: {
          DEFAULT: token('popover'),
          foreground: token('popover-foreground'),
        },
        card: {
          DEFAULT: token('card'),
          foreground: token('card-foreground'),
        },
        surface: {
          1: token('surface-1'),
          2: token('surface-2'),
          3: token('surface-3'),
        },
        sidebar: {
          DEFAULT: token('sidebar'),
          foreground: token('sidebar-foreground'),
          primary: token('sidebar-primary'),
          'primary-foreground': token('sidebar-primary-foreground'),
          accent: token('sidebar-accent'),
          'accent-foreground': token('sidebar-accent-foreground'),
          border: token('sidebar-border'),
          ring: token('sidebar-ring'),
        },
        brand: {
          50: token('brand-50'),
          100: token('brand-100'),
          200: token('brand-200'),
          300: token('brand-300'),
          400: token('brand-400'),
          500: token('brand-500'),
          600: token('brand-600'),
          700: token('brand-700'),
          800: token('brand-800'),
          900: token('brand-900'),
          950: token('brand-950'),
        },
        chart: {
          1: token('chart-1'),
          2: token('chart-2'),
          3: token('chart-3'),
          4: token('chart-4'),
          5: token('chart-5'),
          6: token('chart-6'),
        },
      },
      borderRadius: {
        xl: 'calc(var(--radius) + 2px)',
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      fontFamily: {
        sans: [
          'InterVariable',
          'Inter',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Roboto',
          'Helvetica Neue',
          'Arial',
          'sans-serif',
        ],
        mono: ['ui-monospace', 'SFMono-Regular', 'Cascadia Code', 'Menlo', 'Consolas', 'Liberation Mono', 'monospace'],
      },
      /*
       * Type scale (Tailwind names kept so every page inherits it). Six roles:
       * caption 12 · body 14 · body-lg 16 · title 18/20 · page title 24 · display 30.
       * Tracking follows Inter's own guidance: looser when small, tighter when large.
       */
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem', letterSpacing: '0.01em' }],
        xs: ['0.75rem', { lineHeight: '1rem', letterSpacing: '0.005em' }],
        sm: ['0.875rem', { lineHeight: '1.25rem', letterSpacing: '-0.003em' }],
        base: ['1rem', { lineHeight: '1.5rem', letterSpacing: '-0.006em' }],
        lg: ['1.125rem', { lineHeight: '1.625rem', letterSpacing: '-0.011em' }],
        xl: ['1.25rem', { lineHeight: '1.75rem', letterSpacing: '-0.014em' }],
        '2xl': ['1.5rem', { lineHeight: '2rem', letterSpacing: '-0.019em' }],
        '3xl': ['1.875rem', { lineHeight: '2.25rem', letterSpacing: '-0.021em' }],
        '4xl': ['2.25rem', { lineHeight: '2.5rem', letterSpacing: '-0.022em' }],
      },
      boxShadow: {
        xs: shadow([[1, 2, 0, 0.04]]),
        sm: shadow([
          [1, 2, 0, 0.05],
          [1, 3, 0, 0.04],
        ]),
        DEFAULT: shadow([
          [1, 3, 0, 0.07],
          [1, 2, -1, 0.05],
        ]),
        md: shadow([
          [4, 8, -2, 0.08],
          [2, 4, -2, 0.05],
        ]),
        lg: shadow([
          [12, 24, -6, 0.12],
          [4, 8, -4, 0.06],
        ]),
        xl: shadow([
          [20, 40, -8, 0.16],
          [8, 16, -8, 0.08],
        ]),
      },
      transitionTimingFunction: {
        DEFAULT: 'var(--ease-out)',
        out: 'var(--ease-out)',
      },
      transitionDuration: {
        DEFAULT: '150ms',
      },
      keyframes: {
        'accordion-down': {
          from: { height: '0' },
          to: { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to: { height: '0' },
        },
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out',
        shimmer: 'shimmer 1.6s infinite',
      },
    },
  },
  plugins: [animate],
}

export default config
