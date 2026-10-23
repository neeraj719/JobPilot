/**
 * Display helpers for resume recommendations: labels, the one-line target summary and
 * the per-resume "Mark as done" state.
 *
 * "Done" is a client-side note to self — the server never sees it and the analysis does
 * not change because of it — so it lives in localStorage, keyed by resume id.
 */
import * as React from 'react'
import { SCORE_TEXT, scoreTone } from '@/lib/score'

import type {
  Recommendation,
  RecommendationAction,
  RecommendationCategory,
  RecommendationPriority,
  ResumeTargetSummary,
} from '@/types/api'

export const CATEGORY_LABELS: Record<RecommendationCategory, string> = {
  MISSING_SKILL: 'Missing skill',
  KEYWORD_GAP: 'Keywords',
  WEAK_SUMMARY: 'Summary',
  EXPERIENCE_BULLETS: 'Experience bullets',
  TITLE_ALIGNMENT: 'Title alignment',
  SECTION_MISSING: 'Missing section',
  LENGTH_AND_FORMAT: 'Length & format',
  STALE_CONTENT: 'Older content',
}

export const PRIORITY_LABELS: Record<RecommendationPriority, string> = {
  HIGH: 'High priority',
  MEDIUM: 'Medium priority',
  LOW: 'Low priority',
}

export const ACTION_LABELS: Record<RecommendationAction, string> = {
  add: 'Add if accurate',
  learn: 'Learn',
  list: 'List it',
}

/** Health score colour band: text class used by the gauge and the score figure. */
export function healthColor(score: number): string {
  return SCORE_TEXT[scoreTone(score, 'quality')]
}

export function healthLabel(score: number): string {
  if (score >= 80) return 'Strong'
  if (score >= 60) return 'Needs work'
  return 'Weak'
}

/** "Analysed 25 jobs: mostly Backend Engineer roles asking for Python, PostgreSQL, Docker". */
export function targetSummaryLine(summary: ResumeTargetSummary): string {
  const count = summary.jobs_analysed
  if (count === 0) return 'No target jobs yet.'
  const head = `Analysed ${count} ${count === 1 ? 'job' : 'jobs'}`
  const title = summary.top_titles[0]?.title
  const skills = summary.top_skills.slice(0, 3).map((item) => item.skill)
  const rolePart = title ? `mostly ${title} roles` : ''
  const skillPart = skills.length > 0 ? `asking for ${skills.join(', ')}` : ''
  const tail = [rolePart, skillPart].filter(Boolean).join(' ')
  return tail ? `${head}: ${tail}` : head
}

export function groupByPriority(items: Recommendation[]): [RecommendationPriority, Recommendation[]][] {
  const order: RecommendationPriority[] = ['HIGH', 'MEDIUM', 'LOW']
  return order
    .map((priority) => [priority, items.filter((item) => item.priority === priority)] as [RecommendationPriority, Recommendation[]])
    .filter(([, group]) => group.length > 0)
}

const DONE_KEY_PREFIX = 'jobpilot.resume-recommendations.done.'

function readDone(resumeId: string): string[] {
  try {
    const raw = window.localStorage.getItem(DONE_KEY_PREFIX + resumeId)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.filter((value): value is string => typeof value === 'string') : []
  } catch {
    return []
  }
}

function writeDone(resumeId: string, ids: string[]): void {
  try {
    if (ids.length === 0) window.localStorage.removeItem(DONE_KEY_PREFIX + resumeId)
    else window.localStorage.setItem(DONE_KEY_PREFIX + resumeId, JSON.stringify(ids))
  } catch {
    // Storage can be full or blocked (private mode); the toggle still works for this visit.
  }
}

/** Recommendation ids the user ticked off for this resume, persisted per resume id. */
export function useDoneRecommendations(resumeId: string) {
  const [done, setDone] = React.useState<Set<string>>(() => new Set(readDone(resumeId)))

  React.useEffect(() => {
    setDone(new Set(readDone(resumeId)))
  }, [resumeId])

  const toggle = React.useCallback(
    (id: string) => {
      setDone((previous) => {
        const next = new Set(previous)
        if (next.has(id)) next.delete(id)
        else next.add(id)
        writeDone(resumeId, [...next])
        return next
      })
    },
    [resumeId],
  )

  return { done, toggle }
}
