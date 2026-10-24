import {
  BarChart3,
  ChevronDown,
  Eye,
  History,
  LayoutTemplate,
  PlugZap,
  CircleHelp,
  Cpu,
  FileText,
  Gauge,
  HardDrive,
  KeyRound,
  LogIn,
  PenLine,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  Target,
  UserPlus,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import * as React from 'react'

import { LogoMark } from '@/components/layout/Sidebar'
import { Button } from '@/components/ui/button'
import { type AuthMode, authIntent } from '@/features/auth/authModal'
import { HERO_GLOWS, HeroBackdrop, ON_HERO, STRIP_PILL, STRIP_ROW } from '@/features/landing/heroShared'
import { LANDING_ANCHORS, Wordmark } from '@/features/landing/LandingNav'
import { LANDING_CONTAINER } from '@/features/landing/layout'
import { cn } from '@/lib/utils'

type OpenAuth = (mode: AuthMode) => void

const CONTAINER = LANDING_CONTAINER

/** Eyebrow + display h2 + subline, shared by every section. */
function SectionHeading({ id, eyebrow, title, children, className }: { id: string; eyebrow: string; title: string; children?: React.ReactNode; className?: string }) {
  return (
    <div className={cn('space-y-3', className)}>
      <p className="text-gradient-brand font-display text-sm font-bold tracking-tight">{eyebrow}</p>
      <h2 id={id} className="max-w-[22ch] font-display text-3xl font-semibold tracking-[-0.03em] sm:text-[2.5rem] sm:leading-[1.08] xl:text-[2.875rem]">
        {title}
      </h2>
      {children ? <p className="max-w-prose text-base text-muted-foreground sm:text-lg">{children}</p> : null}
    </div>
  )
}

/** A 3D illustration from public/3d (480 px + 240 px WebP, licences in public/3d/LICENSES.md). */
function Illustration({ name, className, size = 96 }: { name: string; className?: string; size?: number }) {
  return (
    <img
      src={`/3d/${name}-240.webp`}
      srcSet={`/3d/${name}-240.webp 240w, /3d/${name}.webp 480w`}
      sizes={`${size}px`}
      alt=""
      width={size}
      height={size}
      loading="lazy"
      decoding="async"
      className={cn('pointer-events-none shrink-0 select-none drop-shadow-xl', className)}
    />
  )
}

/* ------------------------------------------------------------------ built for */

const BUILT_FOR: { icon: LucideIcon; label: string }[] = [
  { icon: FileText, label: 'Resume Studio' },
  { icon: ScanSearch, label: 'ATS Optimizer' },
  { icon: Target, label: 'Tailored resumes' },
  { icon: Cpu, label: 'Your own AI provider' },
]

export const BuiltForStrip = React.memo(function BuiltForStrip() {
  return (
    <section aria-label="Built for" className="relative w-full" data-landing-strip="">
      <div className={cn(CONTAINER, STRIP_ROW)}>
        <p className="eyebrow">Built for</p>
        <ul className="flex flex-wrap items-center justify-center gap-2 sm:gap-3">
          {BUILT_FOR.map(({ icon: Icon, label }) => (
            <li key={label} className={STRIP_PILL}>
              <Icon className="size-4 text-primary" aria-hidden />
              {label}
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
})

/* ------------------------------------------------------------------ bento */

const TILE = 'relative overflow-hidden rounded-2xl p-6 transition-transform duration-200 ease-out hover:-translate-y-0.5 motion-reduce:hover:translate-y-0'
const PLAIN_TILE = cn(TILE, 'border border-border bg-card shadow-xs dark:shadow-highlight')

const STUDIO_POINTS: { icon: LucideIcon; title: string; body: string }[] = [
  { icon: Eye, title: 'Live preview', body: 'See the printed page while you type.' },
  { icon: LayoutTemplate, title: 'Three templates', body: 'Classic, Modern or Compact.' },
  { icon: History, title: 'Version history', body: 'Compare versions and go back.' },
]
const AI_POINTS: { icon: LucideIcon; text: string }[] = [
  { icon: PlugZap, text: 'Test a connection before you rely on it' },
  { icon: KeyRound, text: 'Keys stored encrypted, shown masked' },
  { icon: BarChart3, text: 'See usage per provider' },
]
const SOURCES = ['Your profile', 'PDF or DOCX', 'Pasted text', 'LinkedIn export']
const PROVIDERS = ['Built-in rules', 'Ollama (local)', 'OpenAI', 'Anthropic', 'Gemini', 'OpenAI-compatible']
const STAGES: { label: string; tone: string }[] = [
  { label: 'Saved', tone: 'bg-secondary text-secondary-foreground' },
  { label: 'Ready to apply', tone: 'bg-info-soft text-info-soft-foreground' },
  { label: 'Applied', tone: 'bg-ai-soft text-ai-soft-foreground' },
  { label: 'Interview', tone: 'bg-success-soft text-success-soft-foreground' },
]
const SUGGESTION_GROUPS: { icon: LucideIcon; title: string; body: string; tone: string }[] = [
  { icon: ShieldCheck, title: 'Ready to apply', body: 'Built only from facts already on your resume or profile.', tone: 'bg-success-soft text-success-soft-foreground' },
  { icon: CircleHelp, title: 'Confirm first', body: 'The posting asks for it; it goes in only if you say it is true.', tone: 'bg-warning-soft text-warning-soft-foreground' },
  { icon: PenLine, title: 'Needs your words', body: 'Results and claims are yours to write — never generated.', tone: 'bg-ai-soft text-ai-soft-foreground' },
]

export const FeatureBento = React.memo(function FeatureBento() {
  return (
    <section id="features" tabIndex={-1} aria-labelledby="features-title" data-landing-section="features" className="w-full scroll-mt-16 outline-none">
      <div className={cn(CONTAINER, 'py-16 sm:py-24')}>
        <SectionHeading id="features-title" eyebrow="Features" title="One studio for every version of your resume">
          Write it once, check it against real postings, and keep a tailored copy for each job — with an AI that stays inside
          what you have actually done.
        </SectionHeading>

        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:auto-rows-[minmax(15rem,auto)] lg:grid-cols-6">
          {/* A: Resume Studio — the hero tile on the brand mesh, with the 3D still. */}
          {/* Light: the soft brand gradient with a soft gradient border and foreground copy.
              Dark: the deep hero band with glows and hero-foreground copy (same rule as the hero). */}
          <article
            data-feature-tile=""
            className={cn(
              TILE,
              'isolate flex min-h-[26rem] flex-col rounded-3xl p-7 text-foreground sm:col-span-2 lg:col-span-4 lg:row-span-2 lg:p-9',
              'dark:text-hero-foreground',
            )}
          >
            <div aria-hidden className="border-gradient-soft pointer-events-none absolute inset-0 -z-10 rounded-3xl dark:hidden" />
            <div aria-hidden className="bg-hero pointer-events-none absolute inset-0 -z-10 hidden dark:block" />
            <div aria-hidden className={cn('pointer-events-none absolute inset-0 -z-10 hidden dark:block', HERO_GLOWS)} />
            {/* Copy and art in their own grid tracks (landing-perf E): the art used to be absolutely
                positioned top-right and sat over the "Version history" card from 1366 px up. */}
            <div className="relative grid items-start gap-6 sm:grid-cols-[minmax(0,1fr)_minmax(0,11rem)] lg:grid-cols-[minmax(0,1fr)_minmax(0,14rem)]">
              <div className="min-w-0 space-y-4">
                <span className="flex size-11 items-center justify-center rounded-xl bg-gradient-brand text-gradient-foreground shadow-glow dark:bg-none dark:bg-hero-foreground/10 dark:text-hero-foreground dark:shadow-none dark:ring-1 dark:ring-inset dark:ring-hero-foreground/20">
                  <FileText className="size-5" aria-hidden />
                </span>
                <h3 className="font-display text-2xl font-semibold tracking-[-0.025em] sm:text-3xl">Write it once, in a real editor</h3>
                <p className="text-muted-foreground dark:text-hero-muted">
                  Start from your profile, a PDF or DOCX, pasted text or your LinkedIn data export. Edit section by section beside a
                  live print preview, pick one of three templates and export to PDF or DOCX. Every save is a version you can go back to.
                </p>
              </div>
              <img
                src="/3d/module-resume.webp"
                srcSet="/3d/module-resume-240.webp 240w, /3d/module-resume.webp 480w"
                sizes="(min-width: 1024px) 224px, 176px"
                alt=""
                width={480}
                height={480}
                loading="lazy"
                decoding="async"
                className="animate-float pointer-events-none hidden aspect-square w-full select-none justify-self-end object-contain drop-shadow-2xl sm:block"
              />
            </div>
            <ul className="relative mt-8 grid gap-3 sm:grid-cols-3">
              {STUDIO_POINTS.map(({ icon: Icon, title, body }) => (
                <li
                  key={title}
                  className="space-y-1.5 rounded-2xl bg-card/80 p-4 ring-1 ring-inset ring-border dark:bg-hero-foreground/10 dark:ring-hero-foreground/15"
                >
                  <Icon className="size-4 text-primary dark:text-hero-foreground" aria-hidden />
                  <span className="block text-sm font-semibold">{title}</span>
                  <span className="block text-sm text-muted-foreground dark:text-hero-muted">{body}</span>
                </li>
              ))}
            </ul>
            <ul aria-label="Ways to start" className="relative mt-auto flex flex-wrap gap-2 pt-8">
              {SOURCES.map((source) => (
                <li
                  key={source}
                  className="rounded-full bg-card/80 px-3 py-1 text-xs font-medium ring-1 ring-inset ring-border dark:bg-hero-foreground/10 dark:ring-hero-foreground/20"
                >
                  {source}
                </li>
              ))}
            </ul>
          </article>

          {/* B: ATS Optimizer. */}
          <article className={cn(PLAIN_TILE, 'flex flex-col gap-4 lg:col-span-2')}>
            <Illustration name="empty-search" size={80} className="-ml-1 -mt-1" />
            <div className="space-y-1.5">
              <h3 className="font-display text-lg font-semibold tracking-tight">Check it against a real posting</h3>
              <p className="text-sm text-muted-foreground">
                Paste a job description to get an estimated match, category scores from fixed rules, and the keywords you have and
                the ones you are missing.
              </p>
            </div>
            <div aria-hidden className="mt-auto space-y-2">
              {['w-[88%]', 'w-[72%]', 'w-[94%]'].map((width) => (
                <span key={width} className="block h-1.5 overflow-hidden rounded-full bg-muted">
                  <span className={cn('block h-full rounded-full bg-gradient-brand', width)} />
                </span>
              ))}
            </div>
          </article>

          {/* C: Tailored resumes. */}
          <article className={cn(PLAIN_TILE, 'flex flex-col gap-4 lg:col-span-2')}>
            <Illustration name="empty-target" size={80} className="-ml-1 -mt-1" />
            <div className="space-y-1.5">
              <h3 className="font-display text-lg font-semibold tracking-tight">One resume per job you want</h3>
              <p className="text-sm text-muted-foreground">
                Save the company, role and posting, make a tailored copy, and follow it from saved to interview with deadlines and
                follow-ups.
              </p>
            </div>
            <ul aria-label="Stages" className="mt-auto flex flex-wrap gap-1.5">
              {STAGES.map((stage) => (
                <li key={stage.label} className={cn('rounded-full px-2.5 py-0.5 text-xs font-medium', stage.tone)}>
                  {stage.label}
                </li>
              ))}
            </ul>
          </article>

          {/* D: Suggestions — the gradient-border tile. */}
          <article className={cn(TILE, 'border-gradient flex flex-col gap-5 shadow-sm sm:col-span-2 lg:col-span-3 dark:shadow-highlight')}>
            <div className="flex items-start gap-4">
              <Illustration name="empty-ai" size={80} className="-ml-1 -mt-1" />
              <div className="space-y-1.5">
                <h3 className="font-display text-lg font-semibold tracking-tight">Suggestions you approve, one by one</h3>
                <p className="text-sm text-muted-foreground">Nothing changes until you press Apply. Every suggestion says which kind it is.</p>
              </div>
            </div>
            <ul className="grid gap-2">
              {SUGGESTION_GROUPS.map(({ icon: Icon, title, body, tone }) => (
                <li key={title} className="flex items-start gap-3 rounded-xl border border-border bg-background/60 p-3">
                  <span className={cn('flex size-7 shrink-0 items-center justify-center rounded-lg', tone)}>
                    <Icon className="size-4" aria-hidden />
                  </span>
                  <span>
                    <span className="block text-sm font-semibold">{title}</span>
                    <span className="block text-sm text-muted-foreground">{body}</span>
                  </span>
                </li>
              ))}
            </ul>
          </article>

          {/* E: AI provider. */}
          <article className={cn(PLAIN_TILE, 'flex flex-col gap-5 sm:col-span-2 lg:col-span-3')}>
            <div className="flex items-start gap-4">
              <Illustration name="empty-settings" size={80} className="-ml-1 -mt-1" />
              <div className="space-y-1.5">
                <h3 className="font-display text-lg font-semibold tracking-tight">Bring your own AI — or none at all</h3>
                <p className="text-sm text-muted-foreground">
                  Built-in rules work with no model. Run a local model with Ollama, or add your own key and choose a model for each
                  task: writing, analysis, rewriting, review.
                </p>
              </div>
            </div>
            <ul className="grid gap-2 sm:grid-cols-3">
              {AI_POINTS.map(({ icon: Icon, text }) => (
                <li key={text} className="flex items-start gap-2 rounded-xl border border-border bg-background/60 p-3 text-sm">
                  <Icon className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
                  {text}
                </li>
              ))}
            </ul>
            <ul aria-label="Supported providers" className="mt-auto flex flex-wrap gap-2">
              {PROVIDERS.map((provider) => (
                <li key={provider} className="rounded-lg border border-border bg-secondary px-2.5 py-1 text-xs font-medium text-secondary-foreground">
                  {provider}
                </li>
              ))}
            </ul>
          </article>
        </div>
      </div>
    </section>
  )
})

/* ------------------------------------------------------------------ how it works */

const STEPS: { slug: string; title: string; body: string; alt: string }[] = [
  {
    slug: 'build',
    title: 'Build or import',
    body: 'Bring what you have — a file, pasted text, your LinkedIn export or your saved profile — and review every section in the editor before you save it.',
    alt: 'The resume editor: sections on the left, the selected section’s fields in the middle and a live print preview on the right.',
  },
  {
    slug: 'score',
    title: 'Score it against a job',
    body: 'Paste the posting. JobPilot reads its requirements, estimates the match by fixed rules you can open and read, and lists the keywords found and missing.',
    alt: 'ATS Optimizer results: an estimated compatibility ring, category scores with their weights, and matched and missing keywords.',
  },
  {
    slug: 'tailor',
    title: 'Tailor with suggestions you approve',
    body: 'Apply safe changes in one click, confirm anything new only if it is true, and write results in your own words. Each change is saved as a new version.',
    alt: 'Recommendations grouped as ready to apply, confirm first and needs your words, each with Apply or Ignore.',
  },
]

export const HowItWorks = React.memo(function HowItWorks() {
  return (
    <section
      id="how-it-works"
      tabIndex={-1}
      aria-labelledby="how-title"
      data-landing-section="how-it-works"
      className="w-full scroll-mt-16 border-y border-border bg-card/50 py-16 outline-none sm:py-24 dark:bg-card/30 [contain-intrinsic-size:auto_900px] [content-visibility:auto]"
    >
      <div className={CONTAINER}>
        <SectionHeading id="how-title" eyebrow="How it works" title="From the resume you have to one made for the job">
          Three steps, all in the same studio. These are real screens from the app.
        </SectionHeading>

        <ol className="mt-12 space-y-14 sm:space-y-20">
          {STEPS.map((step, index) => (
            <li key={step.slug} className="grid items-center gap-6 lg:grid-cols-12 lg:gap-12">
              <div className={cn('space-y-3 lg:col-span-4', index % 2 === 1 && 'lg:order-2')}>
                <span className="text-gradient-brand font-display text-5xl font-bold tracking-[-0.04em]" aria-hidden>
                  {String(index + 1).padStart(2, '0')}
                </span>
                <h3 className="font-display text-2xl font-semibold tracking-[-0.025em]">
                  <span className="sr-only">Step {index + 1}: </span>
                  {step.title}
                </h3>
                <p className="max-w-prose text-muted-foreground">{step.body}</p>
              </div>
              <figure className={cn('lg:col-span-8', index % 2 === 1 && 'lg:order-1')}>
                <div className="rounded-2xl border border-border bg-card p-1.5 shadow-xl dark:shadow-highlight">
                  <img
                    src={`/landing/step-${step.slug}-light.webp`}
                    alt={step.alt}
                    width={1200}
                    height={750}
                    loading="lazy"
                    decoding="async"
                    className="h-auto w-full rounded-xl dark:hidden"
                  />
                  <img
                    src={`/landing/step-${step.slug}-dark.webp`}
                    alt={step.alt}
                    width={1200}
                    height={750}
                    loading="lazy"
                    decoding="async"
                    className="hidden h-auto w-full rounded-xl dark:block"
                  />
                </div>
              </figure>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
})

/* ------------------------------------------------------------------ safety */

const SAFETY: { icon: LucideIcon; title: string; body: string }[] = [
  {
    icon: ShieldCheck,
    title: 'Nothing added without your OK',
    body: 'Suggestions change nothing until you press Apply. A new skill, employer or number goes in only when you confirm it.',
  },
  {
    icon: Gauge,
    title: 'Scores are estimates',
    body: 'The ATS score is JobPilot’s estimate from your resume and the posting — not an employer’s verdict, and not a promise of an interview.',
  },
  {
    icon: HardDrive,
    title: 'Local by default',
    body: 'Built-in rules or a local model do the work, so your resume never leaves your machine unless you choose a hosted provider.',
  },
  {
    icon: KeyRound,
    title: 'Your keys, encrypted',
    body: 'API keys you add are encrypted on the server the moment they arrive and are only ever shown masked.',
  },
]

export const SafetySection = React.memo(function SafetySection() {
  return (
    <section
      id="safety"
      tabIndex={-1}
      aria-labelledby="safety-title"
      data-landing-section="safety"
      className="w-full scroll-mt-16 border-b border-border bg-gradient-brand-soft outline-none [contain-intrinsic-size:auto_900px] [content-visibility:auto]"
    >
      <div className={cn(CONTAINER, 'py-16 sm:py-24')}>
        <SectionHeading id="safety-title" eyebrow="Safety" title="Careful by design">
          A resume is a promise about you. JobPilot treats it that way.
        </SectionHeading>
        <ul className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {SAFETY.map(({ icon: Icon, title, body }) => (
            <li key={title} className="space-y-3 rounded-2xl border border-border bg-card p-5 shadow-xs dark:shadow-highlight">
              <span className="flex size-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <Icon className="size-5" aria-hidden />
              </span>
              <h3 className="font-display text-base font-semibold tracking-tight">{title}</h3>
              <p className="text-sm text-muted-foreground">{body}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
})

/* ------------------------------------------------------------------ FAQ */

const FAQ: { q: string; a: string }[] = [
  {
    q: 'Will the AI make things up on my resume?',
    a: 'No. Every AI output is checked against your resume and profile before you see it. Anything that is not already there — a skill, an employer, a number — is offered as a question you confirm, and results or claims are left for you to write.',
  },
  {
    q: 'Is the ATS score what employers see?',
    a: 'No. It is JobPilot’s estimate, computed by fixed rules from your resume and the job description. Each category shows how it was calculated. Employers use their own systems, and no score guarantees an interview.',
  },
  {
    q: 'Do I need an AI API key?',
    a: 'No. The built-in rules work without any model. You can run a local model with Ollama, or add your own key for OpenAI, Anthropic, Gemini or an OpenAI-compatible endpoint whenever you want.',
  },
  {
    q: 'Where does my resume go?',
    a: 'With the built-in rules or a local model it stays on your machine. If you add a hosted provider, the text needed for that task is sent to the provider you chose — and your key is stored encrypted.',
  },
  {
    q: 'Which formats can I import and export?',
    a: 'Import a PDF or DOCX, paste text, or use the ZIP from LinkedIn’s “Get a copy of your data”. Export to PDF or DOCX in one of three templates.',
  },
  {
    q: 'Does JobPilot apply to jobs for me?',
    a: 'Not today. Automatic job applications are switched off; Resume Studio is the part that is open. You send applications yourself, with a resume made for each one.',
  },
]

export const FaqSection = React.memo(function FaqSection() {
  return (
    <section id="faq" tabIndex={-1} aria-labelledby="faq-title" data-landing-section="faq" className="w-full scroll-mt-16 outline-none [contain-intrinsic-size:auto_900px] [content-visibility:auto]">
      <div className={cn(CONTAINER, 'grid gap-10 py-16 sm:py-24 lg:grid-cols-12 lg:gap-16')}>
        <SectionHeading id="faq-title" eyebrow="FAQ" title="Questions, answered" className="lg:col-span-4">
          The short version of how JobPilot handles your resume.
        </SectionHeading>
        <div className="space-y-3 lg:col-span-8">
          {FAQ.map((item) => (
            <details key={item.q} className="group rounded-2xl border border-border bg-card shadow-xs open:shadow-sm dark:shadow-highlight">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 rounded-2xl px-5 py-4 text-[0.9375rem] font-semibold transition-colors hover:bg-accent/60 [&::-webkit-details-marker]:hidden">
                {item.q}
                <ChevronDown className="size-4 shrink-0 text-muted-foreground transition-transform duration-200 group-open:rotate-180" aria-hidden />
              </summary>
              <p className="max-w-prose px-5 pb-5 text-sm text-muted-foreground">{item.a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  )
})

/* ------------------------------------------------------------------ final CTA + footer */

export const FinalCta = React.memo(function FinalCta({ onOpenAuth }: { onOpenAuth: OpenAuth }) {
  return (
    <section aria-labelledby="cta-title" data-landing-section="cta" className={cn('relative isolate w-full', ON_HERO.title)}>
      <HeroBackdrop fade="both" mirror />
      <div className={cn(CONTAINER, 'relative py-20 text-center sm:py-28')}>
        <div className="mx-auto max-w-3xl space-y-5">
          <Sparkles className="mx-auto size-6 text-primary dark:text-hero-foreground" aria-hidden />
          <h2 id="cta-title" className="font-display text-3xl font-semibold tracking-[-0.03em] sm:text-[2.75rem] sm:leading-[1.05]">
            Start with the resume <span className="text-gradient-brand">you already have.</span>
          </h2>
          <p className={cn('mx-auto max-w-prose sm:text-lg', ON_HERO.body)}>
            Import it, see how it reads against the job you want, and tailor it — every change in your hands.
          </p>
          <div className="flex flex-col justify-center gap-3 pt-2 min-[480px]:flex-row">
            <Button size="lg" className="w-full min-[480px]:w-auto" onClick={() => onOpenAuth('register')} {...authIntent}>
              <UserPlus />
              Create account
            </Button>
            <Button size="lg" variant="outline" className={cn('w-full min-[480px]:w-auto', ON_HERO.outline)} onClick={() => onOpenAuth('login')} {...authIntent}>
              <LogIn />
              Log in
            </Button>
          </div>
        </div>
      </div>
    </section>
  )
})

export const LandingFooter = React.memo(function LandingFooter({ onOpenAuth }: { onOpenAuth: OpenAuth }) {
  return (
    <footer data-landing-section="footer" className="border-t border-border bg-card/50 dark:bg-card/30">
      <div className={cn(CONTAINER, 'flex flex-col gap-8 py-10 md:flex-row md:items-start md:justify-between')}>
        <div className="max-w-xs space-y-3">
          <div className="flex items-center gap-2">
            <LogoMark />
            <Wordmark />
          </div>
          <p className="text-sm text-muted-foreground">Resume tools that stick to your facts.</p>
        </div>
        <nav aria-label="Footer" className="grid grid-cols-2 gap-x-12 gap-y-2 text-sm sm:grid-cols-3">
          {LANDING_ANCHORS.map((anchor) => (
            <a key={anchor.id} href={`#${anchor.id}`} className="rounded-sm py-2.5 text-muted-foreground transition-colors hover:text-foreground md:py-1">
              {anchor.label}
            </a>
          ))}
          <button type="button" onClick={() => onOpenAuth('login')} className="rounded-sm py-2.5 text-left text-muted-foreground transition-colors hover:text-foreground md:py-1">
            Log in
          </button>
          <button type="button" onClick={() => onOpenAuth('register')} className="rounded-sm py-2.5 text-left text-muted-foreground transition-colors hover:text-foreground md:py-1">
            Create account
          </button>
        </nav>
      </div>
      <div className={cn(CONTAINER, 'border-t border-border py-5 text-xs text-muted-foreground')}>
        © {new Date().getFullYear()} JobPilot AI
      </div>
    </footer>
  )
})
