import type { ModuleUnavailableReason } from './types'

export interface UnavailableCopy {
  /** Short badge on a card / menu row. */
  badge: string
  /** One sentence for a tooltip or a card. */
  explanation: string
}

/** The words for each reason a module cannot be opened — one place for every surface. */
export function unavailableCopy(reason: ModuleUnavailableReason | null | undefined): UnavailableCopy {
  switch (reason) {
    case 'platform_disabled':
      return {
        badge: 'Not available right now',
        explanation: 'This module is switched off for everyone at the moment.',
      }
    case 'coming_soon':
      return { badge: 'Coming soon', explanation: 'Not available yet — it is on the way.' }
    case 'disabled_for_user':
      return {
        badge: 'Turned off for your account',
        explanation: 'An administrator turned this module off for your account.',
      }
    default:
      return { badge: 'Unavailable', explanation: 'This module is not part of your workspace right now.' }
  }
}

/** Toast shown when a deep link lands in a module that cannot be opened. */
export function unavailableToast(name: string, reason: ModuleUnavailableReason | null | undefined) {
  switch (reason) {
    case 'platform_disabled':
      return { title: `${name} is not available right now`, description: 'Pick another module to keep going.' }
    case 'coming_soon':
      return { title: `${name} is not available yet`, description: 'Pick another module to keep going.' }
    case 'disabled_for_user':
      return {
        title: `${name} is turned off for your account`,
        description: 'An administrator switched it off. Ask them to turn it back on.',
      }
    default:
      return { title: `${name} is not available`, description: 'It is not part of your workspace right now.' }
  }
}
