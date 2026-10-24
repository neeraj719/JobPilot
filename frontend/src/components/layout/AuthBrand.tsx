import { AUTH_BRAND_ROW, AUTH_BRAND_TEXT } from '@/components/layout/authShell'
import { LogoMark } from '@/components/layout/Sidebar'
import { cn } from '@/lib/utils'

/** Logo mark + "JobPilot AI" wordmark: the header of the auth card, the auth modal and their skeleton. */
export function AuthBrand({ className }: { className?: string }) {
  return (
    <div className={cn(AUTH_BRAND_ROW, className)}>
      <LogoMark className="size-7 rounded-lg [&>svg]:size-3.5" />
      <span className={AUTH_BRAND_TEXT}>
        JobPilot <span className="text-gradient-brand font-bold">AI</span>
      </span>
    </div>
  )
}
