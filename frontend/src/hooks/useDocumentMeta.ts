import * as React from 'react'

import { APP_NAME } from '@/hooks/useDocumentTitle'

export interface DocumentMeta {
  /** Page title; rendered as "<title> · JobPilot AI" unless `rawTitle` is set. */
  title: string
  description: string
  /** Absolute or root-relative image URL for link previews (1200×630). */
  image?: string
  /** Use `title` as-is instead of appending the app name. */
  rawTitle?: boolean
}

type Attr = 'name' | 'property'

/** Find or create `<meta {attr}="{key}">`, set its content, and return a restore function. */
function setMeta(attr: Attr, key: string, content: string): () => void {
  let element = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${key}"]`)
  const created = !element
  if (!element) {
    element = document.createElement('meta')
    element.setAttribute(attr, key)
    document.head.appendChild(element)
  }
  const previous = element.getAttribute('content')
  element.setAttribute('content', content)
  return () => {
    if (!element) return
    if (created) element.remove()
    else if (previous !== null) element.setAttribute('content', previous)
  }
}

function absoluteUrl(path: string): string {
  try {
    return new URL(path, window.location.origin).toString()
  } catch {
    return path
  }
}

/**
 * Title, description, Open Graph and Twitter card tags for a public page (the landing page).
 * Values are restored when the component unmounts, so the app's own pages keep the defaults
 * from `index.html`. Crawlers that do not run JS read those defaults, which describe the
 * same product.
 */
export function useDocumentMeta({ title, description, image, rawTitle = false }: DocumentMeta): void {
  React.useEffect(() => {
    const fullTitle = rawTitle ? title : `${title} · ${APP_NAME}`
    const previousTitle = document.title
    document.title = fullTitle

    const restores = [
      setMeta('name', 'description', description),
      setMeta('property', 'og:type', 'website'),
      setMeta('property', 'og:site_name', APP_NAME),
      setMeta('property', 'og:title', fullTitle),
      setMeta('property', 'og:description', description),
      setMeta('property', 'og:url', absoluteUrl(window.location.pathname)),
      setMeta('name', 'twitter:card', image ? 'summary_large_image' : 'summary'),
      setMeta('name', 'twitter:title', fullTitle),
      setMeta('name', 'twitter:description', description),
    ]
    if (image) {
      const url = absoluteUrl(image)
      restores.push(setMeta('property', 'og:image', url), setMeta('name', 'twitter:image', url))
    }

    return () => {
      document.title = previousTitle
      restores.reverse().forEach((restore) => restore())
    }
  }, [title, description, image, rawTitle])
}
