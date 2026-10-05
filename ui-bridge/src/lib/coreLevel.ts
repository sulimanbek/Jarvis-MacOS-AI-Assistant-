import type { Phase } from '../store'

/**
 * The reactor's loudness, in display-only mode.
 *
 * Normally the page measures its own microphone. In display-only mode the Python
 * core owns the mic, so it streams a 0..1 level (about 15 times a second) and
 * this smooths it into something that moves well at 60fps.
 *
 *   - While you speak it follows your real level.
 *   - While Jarvis speaks there is no audio to measure here (the Mac's own voice
 *     is played by another process), so it follows a synthetic envelope with the
 *     rhythm of speech instead. It is a drawing of talking, not a reading of it.
 *   - At standby the room is only allowed to nudge the ring, so it does not
 *     flicker at every cough.
 */

let target = 0
let shown = 0
let lastFeed = 0

/** A level from the Python core. */
export function feedCoreLevel(x: number) {
  target = Math.max(0, Math.min(1, Number.isFinite(x) ? x : 0))
  lastFeed = performance.now()
}

/** Syllable-like bursts: a fast pulse under a slower phrase rhythm. */
function speakingEnvelope(t: number): number {
  const syllable = Math.pow(Math.abs(Math.sin(2 * Math.PI * 2.7 * t)), 1.4)
  const phrase = 0.6 + 0.4 * Math.sin(2 * Math.PI * 0.55 * t + 1.1)
  const breath = 0.5 + 0.5 * Math.sin(2 * Math.PI * 0.13 * t)
  return Math.min(1, 0.12 + 0.62 * syllable * phrase + 0.12 * breath)
}

const GAIN: Partial<Record<Phase, number>> = {
  waking: 1,
  listening: 1,
  dormant: 0.3,
}

/** Call once per frame. `t` is seconds, `dt` the frame time in seconds. */
export function coreLevel(phase: Phase, t: number, dt: number): number {
  let want: number
  if (phase === 'speaking') {
    want = speakingEnvelope(t)
  } else {
    // A level that stopped arriving is silence, not a held note.
    const stale = performance.now() - lastFeed > 400
    want = stale ? 0 : target * (GAIN[phase] ?? 0)
  }
  // Quick to rise, slower to fall, so a word lands and then settles.
  const k = want > shown ? Math.min(1, dt * 18) : Math.min(1, dt * 6)
  shown += (want - shown) * k
  return shown
}
