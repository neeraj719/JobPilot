/**
 * The landing chunk loader, shared by the router's `React.lazy` and the landing skeleton (which
 * starts the download on mount). The module is cached, so calling it twice costs nothing.
 */
export const loadLanding = () => import('@/pages/Landing')
