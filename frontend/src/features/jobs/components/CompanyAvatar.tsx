import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { cn, initials } from '@/lib/utils'

export interface CompanyAvatarProps {
  name: string | null | undefined
  logoUrl?: string | null
  className?: string
  size?: 'sm' | 'md' | 'lg'
}

const sizes = { sm: 'size-8', md: 'size-10', lg: 'size-14' } as const

/** Company logo with an initials fallback — logo hosts (clearbit) 404 often. */
export function CompanyAvatar({ name, logoUrl, className, size = 'md' }: CompanyAvatarProps) {
  return (
    <Avatar className={cn(sizes[size], 'rounded-lg border border-border bg-muted', className)}>
      {logoUrl ? <AvatarImage src={logoUrl} alt="" className="object-contain p-1" /> : null}
      <AvatarFallback className="rounded-lg bg-muted text-xs font-semibold text-muted-foreground">
        {initials(name)}
      </AvatarFallback>
    </Avatar>
  )
}
