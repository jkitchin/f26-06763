/**
 * What kind of screen the map is on, read from media queries and kept current
 * as the window resizes or a tablet rotates.
 *
 *   touch  the main pointer is a finger (`pointer: coarse`), so there is no
 *          hover: a tap opens, two fingers zoom, and targets are made bigger.
 *   phone  narrower than 640 px: one column, a compact header with a menu,
 *          the panel as a sheet from the bottom, the system figure upright.
 *   wide   1024 px and up: the panel floats at the side of the graph.
 *
 * They combine: a tablet is touch without phone, and wide in landscape. The
 * queries are the user agent's own reading of the device, so a laptop with a
 * touch screen and a mouse reports a fine pointer and keeps hover, which is
 * the right call, since that is what its owner is pointing with.
 */

import { useEffect, useState } from 'react'

const Q = {
  touch: '(pointer: coarse)',
  phone: '(max-width: 639.98px)',
  wide: '(min-width: 1024px)',
} as const

export interface Device { touch: boolean; phone: boolean; wide: boolean }

const read = (): Device => ({
  touch: window.matchMedia(Q.touch).matches,
  phone: window.matchMedia(Q.phone).matches,
  wide: window.matchMedia(Q.wide).matches,
})

export function useDevice(): Device {
  const [d, setD] = useState(read)
  useEffect(() => {
    const ms = Object.values(Q).map((q) => window.matchMedia(q))
    const on = () => setD((prev) => {
      const next = read()
      return prev.touch === next.touch && prev.phone === next.phone && prev.wide === next.wide ? prev : next
    })
    ms.forEach((m) => m.addEventListener('change', on))
    return () => ms.forEach((m) => m.removeEventListener('change', on))
  }, [])
  return d
}
