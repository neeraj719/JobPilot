/**
 * "Save my login", the safe way: hand the credentials to the **browser's own password
 * manager** (encrypted by the OS, filled in by the browser) and keep nothing ourselves.
 *
 * After a successful sign-in, `navigator.credentials.store(new PasswordCredential(...))`
 * asks the browser to offer its usual "Save password?" prompt. Where the Credential
 * Management API is missing (Firefox, Safari) nothing happens here; those browsers
 * still offer to save from the real `<form>` with `autocomplete="email"` /
 * `"current-password"` on the login page.
 *
 * Never write the password to localStorage, sessionStorage, IndexedDB, cookies or the
 * auth store. This function receives it, passes it to the browser and returns.
 */

/** Minimal shape of the non-standard-in-TS `PasswordCredential` constructor (Chromium). */
type PasswordCredentialConstructor = new (data: { id: string; password: string; name?: string }) => Credential

export function offerToSavePassword(details: { email: string; password: string; name?: string | null }): void {
  try {
    const Ctor = (window as unknown as { PasswordCredential?: PasswordCredentialConstructor }).PasswordCredential
    if (!Ctor || !navigator.credentials || typeof navigator.credentials.store !== 'function') return
    const credential = new Ctor({
      id: details.email,
      password: details.password,
      ...(details.name ? { name: details.name } : {}),
    })
    // Fire and forget: the browser shows (or skips) its own prompt; a refusal is fine.
    void navigator.credentials.store(credential).catch(() => undefined)
  } catch {
    // Older browser, insecure context or a policy that forbids it: no prompt, no harm.
  }
}
