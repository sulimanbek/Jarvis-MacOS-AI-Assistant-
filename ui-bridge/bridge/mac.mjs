import { createSdkMcpServer, tool } from '@anthropic-ai/claude-agent-sdk'
import { z } from 'zod'

/**
 * The Mac, through the Python core.
 *
 * Opening an app, playing a song, changing the volume — the Python side already
 * does all of that, with its own tool allowlist, URL rules and voice
 * confirmation. This server is a doorway to it, not a second implementation:
 * the call is sent over the core socket, Python validates and runs it through
 * its executor, and the result comes back as plain text.
 *
 * Only built for a session that came in on the core channel. A browser session
 * has no Python process behind it, so it never sees this tool.
 */

const DESCRIPTION = `Do something on the user's Mac: open an app, play music, change the volume, open a website, run a Shortcut.

Pick exactly one tool and fill only the fields it needs:
  app       { name }                   open an application, e.g. Safari
  music     { query }                  play a song, artist or album in Apple Music
  browser   { target, query? }         open a known website, optionally searching it
  open      { target }                 open something else by name
  system    { action, value? }         volume_up, volume_down, mute, unmute, volume_status,
                                       lock_screen, sleep_display, battery_status,
                                       brightness_up, brightness_down, reminder_add, note_add
  shortcut  { name }                   run a macOS Shortcut

Simple requests like these are usually handled before they reach you, so you
see the ones that were phrased unusually. Use this only when the user actually
asked for the action. Browser, open and shortcut ask the user to confirm out
loud first; if they say no you get a refusal back — accept it and move on.
The reply is the outcome in plain words. Say it briefly; do not read out a
command.`

/**
 * @param {(decision: object) => Promise<{ ok?: boolean, message?: string, error?: string }>} askAction
 *   Sends the decision to the Python core and resolves with its result.
 */
export function macServer(askAction) {
  return createSdkMcpServer({
    name: 'jarvis_mac',
    version: '1.0.0',
    instructions:
      "The user's Mac, through their local assistant. Use it only to carry out " +
      'something they asked for.',
    alwaysLoad: true,
    tools: [
      tool(
        'mac_action',
        DESCRIPTION,
        {
          tool: z.enum(['app', 'music', 'browser', 'open', 'system', 'shortcut']),
          name: z.string().max(120).optional().catch(undefined),
          query: z.string().max(200).optional().catch(undefined),
          target: z.string().max(200).optional().catch(undefined),
          action: z.string().max(60).optional().catch(undefined),
          value: z.string().max(500).optional().catch(undefined),
        },
        async (args) => {
          // Only the fields that were actually given, so Python's validator sees
          // a clean decision rather than a row of undefined.
          const decision = Object.fromEntries(
            Object.entries(args).filter(([, v]) => typeof v === 'string' && v.trim()),
          )
          let reply
          try {
            reply = await askAction(decision)
          } catch (err) {
            return {
              isError: true,
              content: [
                {
                  type: 'text',
                  text:
                    `The Mac side did not answer: ${err?.message ?? err}. ` +
                    'Tell the user you could not do that right now.',
                },
              ],
            }
          }
          const text = String(reply?.message ?? reply?.error ?? '').slice(0, 600)
          return {
            isError: reply?.ok === false,
            content: [{ type: 'text', text: text || (reply?.ok ? 'Done.' : 'That did not work.') }],
          }
        },
      ),
    ],
  })
}
