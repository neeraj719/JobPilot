import * as React from 'react'

const TOKEN_RE = /\s+|[\p{L}\p{N}_'’+#.-]+|[^\s]/gu

type Op = { type: 'same' | 'add' | 'del'; text: string }

/** Word-level LCS diff (small inputs only: a bullet or a summary). */
export function diffWords(before: string, after: string): Op[] {
  const a = before.match(TOKEN_RE) ?? []
  const b = after.match(TOKEN_RE) ?? []
  const cols = b.length + 1
  const table = new Uint16Array((a.length + 1) * cols)
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      table[i * cols + j] =
        a[i] === b[j] ? table[(i + 1) * cols + j + 1] + 1 : Math.max(table[(i + 1) * cols + j], table[i * cols + j + 1])
    }
  }
  const ops: Op[] = []
  const push = (type: Op['type'], text: string) => {
    const last = ops[ops.length - 1]
    if (last && last.type === type) last.text += text
    else ops.push({ type, text })
  }
  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      push('same', a[i])
      i += 1
      j += 1
    } else if (table[(i + 1) * cols + j] >= table[i * cols + j + 1]) {
      push('del', a[i++])
    } else {
      push('add', b[j++])
    }
  }
  while (i < a.length) push('del', a[i++])
  while (j < b.length) push('add', b[j++])
  return ops
}

/** Before → after. Mostly rewritten text is shown as two blocks; light edits inline. */
export function WordDiff({ before, after }: { before: string | null; after: string | null }) {
  if (!after) {
    return before ? <p className="whitespace-pre-line break-words text-sm text-muted-foreground">{before}</p> : null
  }
  if (!before) {
    return (
      <p className="text-sm">
        <ins className="rounded bg-success/15 px-1 no-underline">{after}</ins>
      </p>
    )
  }
  const ops = diffWords(before, after)
  const kept = ops.filter((op) => op.type === 'same').reduce((n, op) => n + (op.text.match(/\S+/g) ?? []).length, 0)
  const total = Math.max(1, (after.match(/\S+/g) ?? []).length)
  if (kept / total < 0.5) {
    return (
      <div className="grid gap-2 text-sm sm:grid-cols-2" aria-label="Before and after">
        <div className="rounded-md border border-border bg-muted/40 p-2.5">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Now</p>
          <p className="whitespace-pre-line break-words text-muted-foreground">{before}</p>
        </div>
        <div className="rounded-md border border-success/30 bg-success/10 p-2.5">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-success">After</p>
          <p className="whitespace-pre-line break-words">{after}</p>
        </div>
      </div>
    )
  }
  return (
    <p className="whitespace-pre-line break-words text-sm leading-relaxed" aria-label="Before and after">
      {ops.map((op, index) =>
        op.type === 'same' ? (
          <React.Fragment key={index}>{op.text}</React.Fragment>
        ) : op.type === 'del' ? (
          <del key={index} className="rounded bg-destructive/10 text-muted-foreground decoration-destructive/70">
            {op.text}
          </del>
        ) : (
          <ins key={index} className="rounded bg-success/15 no-underline">
            {op.text}
          </ins>
        ),
      )}
    </p>
  )
}
