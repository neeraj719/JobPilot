/**
 * Sign-in, sign-up and role choice, as one lazily loaded bundle. Signed-in users never
 * download it, and the auth hero's 3D scene (its own chunk again, loaded from here) stays off
 * every other route.
 */
export { default as ChooseRolePage } from '@/pages/ChooseRole'
export { default as LoginPage } from '@/pages/Login'
export { default as RegisterPage } from '@/pages/Register'
