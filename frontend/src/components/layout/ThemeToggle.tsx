import { Monitor, Moon, Sun } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'
import { type Theme, useUiStore } from '@/stores/ui'

const OPTIONS: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
  { value: 'system', label: 'System', icon: Monitor },
]

export function ThemeToggle() {
  const theme = useUiStore((state) => state.theme)
  const resolvedTheme = useUiStore((state) => state.resolvedTheme)
  const setTheme = useUiStore((state) => state.setTheme)

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={`Theme: ${theme}`}>
          {resolvedTheme === 'dark' ? <Moon /> : <Sun />}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-40">
        <DropdownMenuLabel>Appearance</DropdownMenuLabel>
        {OPTIONS.map((option) => {
          const Icon = option.icon
          return (
            <DropdownMenuItem
              key={option.value}
              onSelect={() => setTheme(option.value)}
              className={cn(theme === option.value && 'bg-accent text-accent-foreground')}
            >
              <Icon />
              {option.label}
            </DropdownMenuItem>
          )
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
