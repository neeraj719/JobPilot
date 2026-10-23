import { ArrowRight, BrainCircuit } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useAiSettings } from '@/features/ai-providers/api'

/** Settings → "AI & browser": points at the per-user AI Model Settings page. */
export function AiProvidersLinkCard() {
  const settings = useAiSettings()
  return (
    <Card className="mb-6">
      <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
            <BrainCircuit className="size-5" aria-hidden />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold">AI Model Settings</p>
            {settings.isLoading ? (
              <Skeleton className="mt-1 h-4 w-56" />
            ) : (
              <p className="text-xs text-muted-foreground">
                {settings.data?.summary ?? 'Choose your AI provider, add your own API key and pick a model per task.'}
              </p>
            )}
          </div>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link to="/resume/ai-settings">
            Open <ArrowRight aria-hidden />
          </Link>
        </Button>
      </CardContent>
    </Card>
  )
}
