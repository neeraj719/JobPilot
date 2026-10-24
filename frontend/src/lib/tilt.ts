import type * as React from 'react'

/**
 * Pointer handlers for the CSS 3D tilt (`.tilt` in index.css): they set `--tilt-x`, `--tilt-y`
 * and `--lift` on the element; the transform itself is CSS (compositor only). Mouse only, and
 * nothing under `prefers-reduced-motion`.
 */
export function tiltHandlers(enabled = true, strength = { x: 6, y: 8, lift: 3 }) {
  if (!enabled) return {}
  return {
    onPointerMove: (event: React.PointerEvent<HTMLElement>) => {
      if (event.pointerType !== 'mouse' || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
      const box = event.currentTarget.getBoundingClientRect()
      const x = (event.clientX - box.left) / box.width - 0.5
      const y = (event.clientY - box.top) / box.height - 0.5
      event.currentTarget.style.setProperty('--tilt-x', `${(-y * strength.x).toFixed(2)}deg`)
      event.currentTarget.style.setProperty('--tilt-y', `${(x * strength.y).toFixed(2)}deg`)
      event.currentTarget.style.setProperty('--lift', `-${strength.lift}px`)
    },
    onPointerLeave: (event: React.PointerEvent<HTMLElement>) => {
      event.currentTarget.style.setProperty('--tilt-x', '0deg')
      event.currentTarget.style.setProperty('--tilt-y', '0deg')
      event.currentTarget.style.setProperty('--lift', '0px')
    },
  }
}
