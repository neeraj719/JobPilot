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
          /** Secondary text and icons on the rail. */
          muted: token('sidebar-muted'),
          /** Section titles (small caps) on the rail. */
          section: token('sidebar-section'),
          /** Raised surface on the rail: the module switcher, rail tooltips. */
          raised: token('sidebar-raised'),
          /** Far end of the active-item gradient bar (v2). */
          glow: token('sidebar-glow'),
        },
        /** v2 brand gradient stops (text-safe: white copy passes on all of them). */
        gradient: {
          from: token('gradient-from'),
          via: token('gradient-via'),
          to: token('gradient-to'),
          foreground: token('gradient-foreground'),
          'soft-from': token('gradient-soft-from'),
          'soft-to': token('gradient-soft-to'),
        },
        glow: { brand: token('glow-brand') },
        glass: { DEFAULT: token('glass'), border: token('glass-border') },
        /** The brand gradient (`.bg-hero` in index.css) and the copy that sits on it. */
        hero: {
          from: token('hero-from'),
          to: token('hero-to'),
          foreground: token('hero-foreground'),
          muted: token('hero-muted'),
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
      /* v2 radius scale: 3xl 24 hero surfaces · 2xl 20 · xl 16 cards · lg 12 menus · md 10
         controls · sm 8 chips. */
      borderRadius: {
        '3xl': 'calc(var(--radius) * 2)',
        '2xl': 'calc(var(--radius) + 8px)',
        xl: 'calc(var(--radius) + 4px)',
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      fontFamily: {
        /** Headings with personality (v2): Bricolage Grotesque, metric-matched fallback. */
        display: ['BricolageGrotesque', 'BricolageFallback', 'InterVariable', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        sans: [
          'InterVariable',
          'InterFallback',
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
       * caption 12 · body 14 · body-lg 16 · title 18/20 · page title 26 · display / KPI 30.
       * Tracking follows Inter's own guidance: looser when small, tighter when large; the
       * page-title and display steps are tighter than Inter's default so headings read as
       * headings (theme-identity), and pair with `font-heading` (650).
       */
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem', letterSpacing: '0.01em' }],
        xs: ['0.75rem', { lineHeight: '1rem', letterSpacing: '0.005em' }],
        sm: ['0.875rem', { lineHeight: '1.25rem', letterSpacing: '-0.003em' }],
        base: ['1rem', { lineHeight: '1.5rem', letterSpacing: '-0.009em' }],
        lg: ['1.125rem', { lineHeight: '1.625rem', letterSpacing: '-0.013em' }],
        xl: ['1.25rem', { lineHeight: '1.75rem', letterSpacing: '-0.017em' }],
        '2xl': ['1.625rem', { lineHeight: '2rem', letterSpacing: '-0.025em' }],
        '3xl': ['1.875rem', { lineHeight: '2.25rem', letterSpacing: '-0.028em' }],
        '4xl': ['2.25rem', { lineHeight: '2.5rem', letterSpacing: '-0.03em' }],
      },
      fontWeight: {
        /** Page titles, the launcher greeting, KPI figures: between semibold and bold. */
        heading: '650',
      },
      backgroundImage: {
        /** The brand gradient (text-safe, identical in both themes). */
        'gradient-brand':
          'linear-gradient(135deg, hsl(var(--gradient-from)) 0%, hsl(var(--gradient-via)) 55%, hsl(var(--gradient-to)) 100%)',
        /** Tinted panel version for AI content and hero tiles (per theme). */
        'gradient-brand-soft': 'linear-gradient(135deg, hsl(var(--gradient-soft-from)) 0%, hsl(var(--gradient-soft-to)) 100%)',
        /** Gradient glyphs (per theme): pair with `bg-clip-text text-transparent` or `.text-gradient-brand`. */
        'gradient-text':
          'linear-gradient(100deg, hsl(var(--gradient-text-from)) 0%, hsl(var(--gradient-text-via)) 50%, hsl(var(--gradient-text-to)) 100%)',
      },
      boxShadow: {
        /** Brand glow: hover on primary actions, the active launcher card, dark-mode heroes. */
        glow: '0 0 0 1px hsl(var(--glow-brand) / 0.18), 0 10px 32px -8px hsl(var(--glow-brand) / 0.55)',
        /** 1 px inner highlight on raised dark surfaces (and glass). */
        highlight: 'inset 0 1px 0 0 hsl(var(--glass-border) / 0.08)',
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
        /** Long soft deceleration for panels that travel (the sidebar rail). */
        drawer: 'var(--ease-drawer)',
      },
      transitionDuration: {
        DEFAULT: '150ms',
      },
      keyframes: {
        /** Cards and list rows entering (stagger with `style={{ '--i': n }}`). */
        'rise-in': {
          from: { opacity: '0', transform: 'translateY(10px) scale(0.985)' },
          to: { opacity: '1', transform: 'none' },
        },
        /** Route change: short fade + 4 px lift, 180 ms. */
        'page-in': {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to: { opacity: '1', transform: 'none' },
        },
        /** Slow idle bob for pre-rendered 3D illustrations. */
        float: {
          '0%, 100%': { transform: 'translateY(0) rotate(0deg)' },
          '50%': { transform: 'translateY(-6px) rotate(-1.5deg)' },
        },
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
        'rise-in': 'rise-in 420ms var(--ease-spring) both',
        'page-in': 'page-in 180ms var(--ease-out) both',
        float: 'float 6s ease-in-out infinite',
      },
    },
  },
  plugins: [animate],
}

export default config
