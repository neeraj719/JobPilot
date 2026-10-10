# JobPilot AI — frontend

React 18 + TypeScript + Vite + Tailwind + hand-written shadcn/ui components.
This package is the **dashboard shell**: routing, auth, layout, the design system and the
typed API client. Feature pages are filled in on top of it.

## Commands

```bash
cd frontend
npm install

npm run dev         # Vite dev server on http://localhost:5173
npm run typecheck   # tsc --noEmit (strict)
npm run build       # typecheck + production build into dist/
npm run preview     # serve dist/ on http://localhost:4173
```

The dev server proxies `/api` and `/demo-ats` to `http://localhost:8000`, so run the backend
(`uvicorn app.main:app --reload` or `docker compose up`) alongside it. Override the target with
`VITE_DEV_BACKEND_URL`.

Copy `.env.example` to `.env` if you need to change `VITE_API_BASE_URL` (default `/api/v1`).
In Docker the value is baked at build time by `Dockerfile` (`ARG VITE_API_BASE_URL`) and nginx
proxies `/api/` and `/demo-ats/` to the `backend` service.

## Folder layout

```
src/
  components/
    ui/          shadcn-style primitives (button, card, dialog, form, table, …)
    common/      app-level building blocks (StatusBadge, MatchScore, DataTable, EmptyState, …)
    layout/      AppShell, Sidebar, Topbar, PageHeader, PageContainer, AuthLayout
  features/
    <area>/api.ts   react-query hooks for one API area  <-- page agents add these
    <area>/…        components used only by that area
  hooks/         useAuth, useDebounce, useDocumentTitle
  lib/           api.ts (fetch client), queryClient.ts (+ query keys), utils.ts (cn, formatters)
  pages/         one default-exported page component per route
  stores/        zustand stores (auth, ui)
  types/api.ts   enums + response shapes mirroring the backend contract
```

## Conventions for page agents

### 1. Data fetching lives in `src/features/<area>/api.ts`

Never call `fetch` from a component. Write react-query hooks in the feature's `api.ts`, built on
the typed client and the shared query keys. `src/features/notifications/api.ts` is the reference
implementation.

```ts
// src/features/jobs/api.ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { qk } from '@/lib/queryClient'
import type { JobCard, JobDetail, JobListParams, PageResponse } from '@/types/api'

export function useJobs(params: JobListParams) {
  return useQuery({
    queryKey: qk.jobs.list(params),
    queryFn: () => api.get<PageResponse<JobCard>>('/jobs', { params: { ...params } }),
  })
}

export function useJob(id: string) {
  return useQuery({ queryKey: qk.jobs.detail(id), queryFn: () => api.get<JobDetail>(`/jobs/${id}`) })
}

export function useQueueJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (jobId: string) => api.post(`/jobs/${jobId}/queue`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.jobs.all })
      void queryClient.invalidateQueries({ queryKey: qk.applications.all })
    },
  })
}
```

Add your keys to `qk` in `src/lib/queryClient.ts` rather than inventing loose strings — that is
what makes cross-feature invalidation work.

### 2. The API client

`api.get/post/put/patch/delete<T>(path, body?, { params })`, plus `api.upload(path, formData)` and
`api.download(path)` (returns a `Blob`; pair it with `saveBlob`). Paths are relative to
`VITE_API_BASE_URL`, so use `/jobs`, not `/api/v1/jobs`.

- The `Authorization: Bearer` header is attached automatically from the auth store.
- A 401 on an authenticated request triggers one `POST /auth/refresh` (cookie-based) and a retry.
- Failures throw `ApiError { status, code, message, details }`. Use `isApiError(err)` /
  `errorMessage(err)` from `@/lib/api` — `ErrorState` already does.

### 3. Page structure

One default export per file in `src/pages`. Keep the wrapper:

```tsx
export default function JobsPage() {
  const { data, isLoading, error, refetch } = useJobs(params)
  return (
    <PageContainer>
      <PageHeader title="Jobs" description="…" actions={<Button>Discover jobs</Button>} />
      {error ? <ErrorState error={error} onRetry={refetch} /> : null}
      {isLoading ? <LoadingState variant="cards" /> : null}
      …
    </PageContainer>
  )
}
```

Routes are declared in `src/router.tsx`; the sidebar entries live in
`src/components/layout/navigation.ts`. Adding a route means touching both.

### 4. Shared display components (`@/components/common`)

| Component | Use it for |
|---|---|
| `<StatusBadge status={app.status} />` | any `ApplicationStatus` — label + colour come from the shared maps |
| `<MatchScore score={job.match_score} showBar />` | 0–100 score pill; bands are 85+ green, 70+ amber, else muted |
| `<PriorityBadge priority={job.company_priority} />` | P1 / P2 / P3 / Avoid |
| `<SourceBadge source="LINKEDIN" />`, `<SourceBadgeList sources={job.sources} />` | platform provenance |
| `<StatCard title="Applied today" value={12} delta={3} icon={Send} />` | KPI tiles |
| `<DataTable data={items} columns={cols} onRowClick={…} />` | typed tables with built-in loading / empty / error states |
| `<EmptyState />`, `<ErrorState error onRetry />`, `<LoadingState variant="cards" />` | the three non-happy states — always render all three |
| `<ConfirmDialog />` | destructive actions (withdraw, delete, disconnect) |
| `<Pagination page pageSize total onPageChange />` | every `PageResponse<T>` list |

Never hand-roll a status colour: use `statusColor`, `matchScoreColor`, `priorityColor`,
`sourceLabel` and friends from `@/lib/utils` so the palette stays consistent.

### 5. Formatting helpers (`@/lib/utils`)

`cn`, `formatCurrency` (INR renders as `₹12.0 LPA`), `formatSalaryRange`, `formatDate`,
`formatDateTime`, `formatRelative`, `formatExperience`, `formatPercent`, `formatCompactNumber`,
`initials`, `truncate`, `humanizeEnum`, `slugify`, `pluralize`.

### 6. Styling

Tailwind with the shadcn CSS-variable theme (`src/index.css`); `darkMode: 'class'` driven by the
UI store. Use the semantic tokens (`bg-card`, `text-muted-foreground`, `border-border`,
`text-success`, `bg-warning/15`, `bg-chart-1`, …) instead of raw palette colours so both themes
keep working. Chart series should use `hsl(var(--chart-1))` … `hsl(var(--chart-5))`.

### 7. Forms

`react-hook-form` + `zod` via `@hookform/resolvers/zod`, rendered with the `Form*` components in
`@/components/ui/form`. `src/pages/Login.tsx` and `src/pages/Register.tsx` are working examples.
Report failures with `toast.error(...)` from `sonner` (re-exported by `@/components/ui/toaster`).

### 8. Types

`src/types/api.ts` mirrors `backend/app/models/enums.py` and `docs/CONTRACTS.md`. Fields marked
`NOTE:` were inferred where the contract was open-ended — reconcile them against the live schema
at `http://localhost:8000/openapi.json` (or `/docs`) before depending on them, and update the
type rather than casting at the call site.

Each enum ships as a `const` tuple plus a union type, so filter dropdowns can iterate the values:

```tsx
{APPLICATION_STATUSES.map((status) => (
  <SelectItem key={status} value={status}>{APPLICATION_STATUS_LABELS[status]}</SelectItem>
))}
```

## Auth

`src/stores/auth.ts` (zustand + persist to `sessionStorage`) holds `accessToken` and `user`.
`App.tsx` calls `bootstrap()` on mount, which validates a restored token via `GET /auth/me`;
`ProtectedRoute` waits for that before redirecting. The refresh token is an HttpOnly cookie owned
by the backend — the frontend never reads it. Use `useAuth()` in components.
