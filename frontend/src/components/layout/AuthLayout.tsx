import { Bot, Radar, ShieldCheck } from 'lucide-react'
import * as React from 'react'

import { ThemeToggle } from '@/components/layout/ThemeToggle'

const HIGHLIGHTS = [
  {
    icon: Radar,
    title: 'Finds the right roles',
    body: 'Discovers postings across platforms, removes duplicates and scores each one against your resume.',
  },
  {
    icon: Bot,
    title: 'Prepares the application',
    body: 'Drafts answers from facts you provided — never invented — and fills the form for you.',
  },
  {
    icon: ShieldCheck,
    title: 'You approve every send',
    body: 'Anything it cannot answer pauses for review. No CAPTCHA, OTP or 2FA is ever bypassed.',
  },
]

export interface AuthLayoutProps {
  title: string
  description: string
  children: React.ReactNode
  footer?: React.ReactNode
}

/** Split layout shared by the sign-in and sign-up screens. */
export function AuthLayout({ title, description, children, footer }: AuthLayoutProps) {
  return (
    <div className="grid min-h-svh lg:grid-cols-2">
      <div className="relative hidden flex-col justify-between bg-gradient-to-br from-[hsl(var(--hero-from))] to-[hsl(var(--hero-to))] p-10 text-white lg:flex">
        <div className="flex items-center gap-2.5">
          <span className="flex size-9 items-center justify-center rounded-lg bg-white/15">
            <svg viewBox="0 0 24 24" className="size-5" fill="currentColor" aria-hidden>
              <path d="M20.3 3.9 5.6 9.8c-.9.4-.9 1.6 0 2l5.1 2.2 2.3 5.2c.4.9 1.6.8 2-.1l5.9-14.3c.3-.8-.4-1.5-1.2-1.2Z" />
            </svg>
          </span>
          <span className="text-lg font-semibold">JobPilot AI</span>
        </div>

        <div className="space-y-8">
          <h2 className="max-w-md text-3xl font-semibold leading-tight text-balance">
            Your job search, running in the background.
          </h2>
          <ul className="space-y-6">
            {HIGHLIGHTS.map((item) => {
              const Icon = item.icon
              return (
                <li key={item.title} className="flex gap-3">
                  <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-white/15">
                    <Icon className="size-4" aria-hidden />
                  </span>
                  <span className="space-y-1">
                    <span className="block text-sm font-semibold">{item.title}</span>
                    <span className="block max-w-sm text-sm text-white/75">{item.body}</span>
                  </span>
                </li>
              )
            })}
          </ul>
        </div>

        <p className="text-xs text-white/70">
          Applications are only submitted after you approve them.
        </p>
      </div>

      <div className="relative flex items-center justify-center px-4 py-12 sm:px-8">
        <div className="absolute right-4 top-4">
          <ThemeToggle />
        </div>
        <div className="w-full max-w-sm space-y-6">
          <div className="space-y-2 text-center lg:text-left">
            <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
            <p className="text-sm text-muted-foreground">{description}</p>
          </div>
          {children}
          {footer ? <div className="text-center text-sm text-muted-foreground">{footer}</div> : null}
        </div>
      </div>
    </div>
  )
}
