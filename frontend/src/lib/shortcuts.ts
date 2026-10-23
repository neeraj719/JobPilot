/** Keyboard shortcut labels shown in tooltips, adapted to the user's platform. */
export const IS_MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)

/** Toggles the sidebar (handled in AppShell). */
export const SIDEBAR_SHORTCUT_LABEL = IS_MAC ? '⌘B' : 'Ctrl+B'

/** Opens the module switcher (handled in AppShell). Ctrl+K is left free for a future search. */
export const MODULE_SWITCHER_SHORTCUT_LABEL = IS_MAC ? '⇧⌘M' : 'Ctrl+Shift+M'

/** True for Ctrl+Shift+M / Cmd+Shift+M. */
export function isModuleSwitcherShortcut(event: KeyboardEvent): boolean {
  return event.key.toLowerCase() === 'm' && (event.metaKey || event.ctrlKey) && event.shiftKey && !event.altKey
}
