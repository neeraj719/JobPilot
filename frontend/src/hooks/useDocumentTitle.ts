import * as React from 'react'

export const APP_NAME = 'JobPilot AI'

/**
 * Set `document.title` to `"<title> · JobPilot AI"` while the component is mounted, and
 * restore the previous title on unmount. Pass `undefined` to show just the app name.
 */
export function useDocumentTitle(title?: string | null): void {
  React.useEffect(() => {
    const previous = document.title
    document.title = title ? `${title} · ${APP_NAME}` : APP_NAME
    return () => {
      document.title = previous
    }
  }, [title])
}
