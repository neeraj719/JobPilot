/** Plain-language copy shared by the Create Resume panel and the Settings card. */

/** `?error=` codes the OAuth callback can redirect with. */
export const LINKEDIN_ERRORS: Record<string, string> = {
  access_denied: 'You cancelled on LinkedIn, so nothing was connected.',
  invalid_state: 'That sign-in link was already used or is not valid. Start the connection again.',
  state_expired: 'The LinkedIn sign-in took longer than 10 minutes. Start the connection again.',
  state_mismatch: 'The sign-in finished in a different browser than it started in. Start again here.',
  nonce_mismatch: 'LinkedIn’s answer did not match this sign-in. Start the connection again.',
  token_exchange_failed: 'LinkedIn did not complete the sign-in. Try connecting again.',
  linkedin_code_rejected: 'LinkedIn did not accept the sign-in code. Start again from Create Resume; do not reuse an old tab.',
  userinfo_failed: 'LinkedIn did not return your basic details. Try connecting again.',
  id_token_invalid: 'LinkedIn’s answer could not be verified. Try connecting again.',
  id_token_missing: 'LinkedIn’s answer could not be verified. Try connecting again.',
  linkedin_unreachable: 'LinkedIn could not be reached. Try again in a moment.',
  not_configured: 'LinkedIn is not configured on this server yet.',
  connection_failed: 'LinkedIn did not complete the connection. Try again.',
}

export function linkedinErrorMessage(code: string | null | undefined): string {
  if (!code) return LINKEDIN_ERRORS.connection_failed
  return LINKEDIN_ERRORS[code] ?? LINKEDIN_ERRORS.connection_failed
}

/** What each path yields — shown before connecting, so nobody expects more than LinkedIn shares. */
export const WHAT_LINKEDIN_SHARES: { title: string; body: string }[] = [
  {
    title: 'Instantly: name, email and photo',
    body: 'LinkedIn’s official sign-in (OpenID Connect) shares only these basics — not positions, education or skills.',
  },
  {
    title: 'Full history: your LinkedIn export',
    body: 'Positions, education, skills and certifications come from the ZIP you download from LinkedIn (or, for EU/EEA members, LinkedIn’s data-portability API when this server has it enabled).',
  },
  {
    title: 'You review every change',
    body: 'Nothing is written to your profile until you tick it. JobPilot never scrapes LinkedIn and never signs in as you.',
  },
]

export const SCOPE_LABELS: Record<string, string> = {
  openid: 'Sign in',
  profile: 'Name and photo',
  email: 'Email address',
  r_dma_portability_3rd_party: 'Full profile (data portability)',
}
