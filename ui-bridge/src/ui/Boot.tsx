import { AnimatePresence, motion } from 'framer-motion'
import { useStore } from '../store'

/**
 * The start-up: a thin ring draws itself and the name fades in. Nothing else.
 *
 * It used to be a nine-second, four-beat sequence — boot log, reticles, a suit
 * schematic, a reactor lighting up. This keeps the same hand-off (App waits
 * BOOT_MS, then the live scene takes over) in under two seconds.
 */

/** How long App waits before handing over to the live interface. */
export const BOOT_MS = 1800

export function Boot() {
  const phase = useStore((s) => s.phase)
  if (phase !== 'boot') return null

  return (
    <AnimatePresence>
      <motion.div
        className="boot"
        initial={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.6 }}
      >
        <div className="boot-min">
          <svg className="boot-min-ring" viewBox="0 0 100 100" aria-hidden="true">
            <circle cx="50" cy="50" r="46" pathLength="1" />
          </svg>
          <span className="boot-min-name">Jarvis</span>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}
