import { FileText, ScanSearch, ShieldCheck } from 'lucide-react'
import * as React from 'react'

import { AuthBrand } from '@/components/layout/AuthBrand'
import { LogoMark } from '@/components/layout/Sidebar'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import {
  AUTH_CARD,
  AUTH_CARD_HEAD,
  AUTH_DESCRIPTION,
  AUTH_FOOTER,
  AUTH_FORM_COL,
  AUTH_GRID,
  AUTH_HERO,
  AUTH_HERO_ART,
  AUTH_HERO_ART_BOX,
  AUTH_HERO_BODY,
  AUTH_HERO_BRAND,
  AUTH_HERO_BRAND_TEXT,
  AUTH_HERO_CHIP,
  AUTH_HERO_DEFAULT_TITLE,
  AUTH_HERO_ITEM,
  AUTH_HERO_ITEM_BODY,
  AUTH_HERO_ITEM_TITLE,
  AUTH_HERO_LIST,
  AUTH_HERO_NOTE,
  AUTH_HERO_NOTE_TEXT,
  AUTH_HERO_TITLE,
  AUTH_HIGHLIGHTS,
  AUTH_TITLE,
} from '@/components/layout/authShell'
import { AuthHero3D } from '@/features/brand-3d/AuthHero3D'
import { cn } from '@/lib/utils'
import { loadHome, prefetchWhenIdle } from '@/modules/prefetch'

const HIGHLIGHT_ICONS = [FileText, ScanSearch, ShieldCheck]

export interface AuthLayoutProps {
  title: string
  description: string
  children: React.ReactNode
  footer?: React.ReactNode
  /** The display headline on the brand hero (lg+). */
  heroTitle?: string
}

/**
 * Split layout shared by the sign-in, sign-up and role screens (v2). Every class and string
 * that decides a box comes from `authShell.ts`, which `AuthSkeleton` renders too — so the
 * skeleton has this page's exact geometry and nothing moves when the chunk arrives.
 */
export function AuthLayout({ title, description, children, footer, heroTitle = AUTH_HERO_DEFAULT_TITLE }: AuthLayoutProps) {
  // Signing in leads to the launcher: fetch its chunk while the visitor types.
  React.useEffect(() => prefetchWhenIdle(loadHome), [])
  return (
    <div className={AUTH_GRID}>
      {/* Brand hero: the brand gradient mesh (`.bg-hero`), a glow, the interactive 3D object
          (lazy chunk, static still as fallback) and the pitch. Identical in both themes. */}
      <div className={AUTH_HERO} data-auth-hero-panel="">
        <div aria-hidden className="pointer-events-none absolute inset-y-0 right-0 w-3/4 bg-[radial-gradient(closest-side,hsl(var(--glow-brand)/0.32),transparent)]" />
        <div aria-hidden className="pointer-events-none absolute bottom-0 left-0 h-1/2 w-2/3 bg-[radial-gradient(closest-side,hsl(var(--gradient-to)/0.28),transparent)]" />

        <div className={AUTH_HERO_BRAND}>
          <LogoMark className="size-9 ring-hero-foreground/20 [&>svg]:size-5" />
          <span className={AUTH_HERO_BRAND_TEXT}>JobPilot AI</span>
        </div>

        <div className={AUTH_HERO_ART}>
          <AuthHero3D className={AUTH_HERO_ART_BOX} />
        </div>
        <p className="sr-only">Illustration: a resume card with a match score chip and a check badge.</p>

        <div className={AUTH_HERO_BODY} data-auth-hero-text="">
          <h2 className={AUTH_HERO_TITLE}>{heroTitle}</h2>
          <ul className={AUTH_HERO_LIST}>
            {AUTH_HIGHLIGHTS.map((item, index) => {
              const Icon = HIGHLIGHT_ICONS[index] ?? FileText
              return (
                <li key={item.title} className={AUTH_HERO_ITEM}>
                  <span className={cn(AUTH_HERO_CHIP, 'bg-hero-foreground/10 ring-1 ring-inset ring-hero-foreground/15 backdrop-blur-sm')}>
                    <Icon className="size-4" aria-hidden />
                  </span>
                  <span className="space-y-0.5">
                    <span className={AUTH_HERO_ITEM_TITLE}>{item.title}</span>
                    <span className={cn(AUTH_HERO_ITEM_BODY, 'text-hero-muted')}>{item.body}</span>
                  </span>
                </li>
              )
            })}
          </ul>
        </div>

        <p className={cn(AUTH_HERO_NOTE, 'text-hero-muted')}>{AUTH_HERO_NOTE_TEXT}</p>
      </div>

      {/* Form side: soft brand glows behind a glass card. */}
      <div className={AUTH_FORM_COL}>
        <div aria-hidden className="pointer-events-none absolute right-0 top-0 h-1/2 w-2/3 bg-[radial-gradient(closest-side,hsl(var(--glow-brand)/0.2),transparent)]" />
        <div aria-hidden className="pointer-events-none absolute bottom-0 left-0 h-1/2 w-2/3 bg-[radial-gradient(closest-side,hsl(var(--gradient-to)/0.12),transparent)]" />
        <div className="absolute right-4 top-4 z-10">
          <ThemeToggle />
        </div>
        <div className={AUTH_CARD} data-auth-card="">
          <div className={AUTH_CARD_HEAD}>
            <AuthBrand />
            <h1 className={AUTH_TITLE}>{title}</h1>
            <p className={AUTH_DESCRIPTION}>{description}</p>
          </div>
          {children}
          {footer ? <div className={AUTH_FOOTER}>{footer}</div> : null}
        </div>
      </div>
    </div>
  )
}
