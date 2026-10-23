/** Keyboard shortcut labels shown in tooltips, adapted to the user's platform. */
export const IS_MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)

/** Toggles the sidebar (handled in AppShell). */
export const SIDEBAR_SHORTCUT_LABEL = IS_MAC ? '⌘B' : 'Ctrl+B'
