import * as React from 'react'

import { cn } from '@/lib/utils'

/** three + fiber + drei: a chunk of its own, requested only when this component decides to. */
const HeroScene = React.lazy(() => import('@/features/brand-3d/HeroScene'))

/** Pre-rendered still of the same scene (rendered from HeroScene itself). */
const STATIC_SRC = '/3d/hero-scene.webp'
const STATIC_SRCSET = '/3d/hero-scene-640.webp 640w, /3d/hero-scene.webp 1120w'

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function hasWebGL(): boolean {
  try {
    const canvas = document.createElement('canvas')
    return Boolean(canvas.getContext('webgl2') ?? canvas.getContext('webgl'))
  } catch {
    return false
  }
}

/** The interactive scene only where it will run well: motion allowed, ≥ 4 cores, WebGL. */
function canRun3D(minWidth = 0): boolean {
  if (typeof window === 'undefined') return false
  if (prefersReducedMotion()) return false
  if (minWidth > 0 && window.innerWidth < minWidth) return false
  if ((navigator.hardwareConcurrency ?? 8) < 4) return false
  return hasWebGL()
}

class SceneBoundary extends React.Component<{ onError: () => void; children: React.ReactNode }, { failed: boolean }> {
  override state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  override componentDidCatch() {
    this.props.onError()
  }

  override render() {
    return this.state.failed ? null : this.props.children
  }
}

/**
 * The sign-in hero's 3D object. Renders the static still first (no layout shift, works without
 * JS-heavy WebGL), then fades the live scene in over it once its first frame is drawn. Falls
 * back to the still for reduced motion, low-end devices and WebGL errors. Decorative only.
 */
export interface AuthHero3DProps {
  className?: string
  /**
   * The poster is the page's LCP candidate (the landing hero): load it eagerly with high
   * fetch priority. Off by default (the auth hero keeps its current loading behaviour).
   */
  priority?: boolean
  /** `sizes` for the poster's srcset; defaults to the auth hero's column width. */
  sizes?: string
  /** Below this viewport width the poster is shown instead of the live scene (0 = always live). */
  liveMinWidth?: number
  /**
   * When the live scene may start: `idle` (after first paint, idle, on screen — the auth
   * hero) or `interaction` (additionally after the first pointer / scroll / key input — the
   * landing hero, so a passive page load never pays for three.js).
   */
  liveOn?: 'idle' | 'interaction'
}

export function AuthHero3D({
  className,
  priority = false,
  sizes = '(min-width: 1280px) 560px, 44vw',
  liveMinWidth = 0,
  liveOn = 'idle',
}: AuthHero3DProps) {
  const [live, setLive] = React.useState(false)
  const [ready, setReady] = React.useState(false)
  const boxRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    // The live scene mounts only when ALL of these hold: the first contentful paint has
    // happened (the poster is the LCP element), the main thread is idle, the box is on
    // screen, and — for `liveOn="interaction"` — the visitor has moved, scrolled, tapped or
    // typed. Until then the identical poster is shown and three.js is not even downloaded.
    let cancelled = false
    const cleanups: (() => void)[] = []
    const gates = { painted: false, visible: false, engaged: liveOn === 'idle' }
    let idle: number | undefined

    const decide = () => {
      if (cancelled || !gates.painted || !gates.visible || !gates.engaged) return
      if (idle !== undefined) return
      const run = () => !cancelled && setLive(canRun3D(liveMinWidth))
      idle = 'requestIdleCallback' in window ? window.requestIdleCallback(run, { timeout: 1500 }) : (setTimeout(run, 120) as unknown as number)
    }

    // 1. After the first contentful paint (a paint entry, not a guess from rAF timing).
    const onPainted = () => {
      gates.painted = true
      decide()
    }
    if (performance.getEntriesByName('first-contentful-paint').length) onPainted()
    else if (typeof PerformanceObserver !== 'undefined' && PerformanceObserver.supportedEntryTypes?.includes('paint')) {
      const observer = new PerformanceObserver((list) => {
        if (list.getEntriesByName('first-contentful-paint').length) {
          observer.disconnect()
          onPainted()
        }
      })
      observer.observe({ type: 'paint', buffered: true })
      cleanups.push(() => observer.disconnect())
    } else {
      const timer = setTimeout(onPainted, 1000)
      cleanups.push(() => clearTimeout(timer))
    }

    // 2. Only while the box is on screen.
    const node = boxRef.current
    if (node && 'IntersectionObserver' in window) {
      const io = new IntersectionObserver((entries) => {
        gates.visible = entries.some((entry) => entry.isIntersecting)
        decide()
      })
      io.observe(node)
      cleanups.push(() => io.disconnect())
    } else gates.visible = true

    // 3. Optionally, after the first interaction.
    if (!gates.engaged) {
      const events = ['pointermove', 'pointerdown', 'keydown', 'wheel', 'touchstart', 'scroll'] as const
      const onEngage = () => {
        gates.engaged = true
        events.forEach((type) => window.removeEventListener(type, onEngage))
        decide()
      }
      events.forEach((type) => window.addEventListener(type, onEngage, { passive: true }))
      cleanups.push(() => events.forEach((type) => window.removeEventListener(type, onEngage)))
    }

    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onMotionChange = () => setLive(canRun3D(liveMinWidth))
    media.addEventListener('change', onMotionChange)
    cleanups.push(() => media.removeEventListener('change', onMotionChange))

    return () => {
      cancelled = true
      if (idle !== undefined) {
        if ('cancelIdleCallback' in window) window.cancelIdleCallback(idle)
        clearTimeout(idle)
      }
      cleanups.forEach((cleanup) => cleanup())
    }
  }, [liveMinWidth, liveOn])

  return (
    <div ref={boxRef} className={cn('relative', className)} aria-hidden data-hero-3d={live ? (ready ? 'live' : 'loading') : 'static'}>
      <img
        src={STATIC_SRC}
        srcSet={STATIC_SRCSET}
        sizes={sizes}
        alt=""
        width={1120}
        height={1120}
        decoding="async"
        loading={priority ? 'eager' : undefined}
        // Lower-case attribute: React 18 does not know the `fetchPriority` prop yet.
        {...(priority ? { fetchpriority: 'high' } : {})}
        className={cn(
          'absolute inset-0 size-full object-contain transition-opacity duration-500 motion-reduce:transition-none',
          live && ready ? 'opacity-0' : 'opacity-100',
        )}
      />
      {live ? (
        <SceneBoundary onError={() => setLive(false)}>
          <React.Suspense fallback={null}>
            <HeroScene
              onReady={() => setReady(true)}
              className={cn('!absolute inset-0 transition-opacity duration-700', ready ? 'opacity-100' : 'opacity-0')}
            />
          </React.Suspense>
        </SceneBoundary>
      ) : null}
    </div>
  )
}
