/**
 * The one interactive 3D scene in the product: the landing / sign-in / sign-up hero.
 *
 * v3 (owner review, 2026-10-24): fewer, better objects — a matte resume card with extruded
 * lines and a photo chip, a floating "match" chip with a warm score arc, and a check badge.
 * Physical materials lit by a procedural environment (drei `<Environment>` with
 * `<Lightformer>`s: no HDR download), a contact shadow for grounding, a slow `<Float>` idle,
 * a staggered spring entrance and a pointer parallax limited to ±6°.
 *
 * It is ONLY ever imported through `React.lazy` from `AuthHero3D`, so three / fiber / drei
 * stay in this chunk. Colours come from the CSS tokens (`--brand-*`, `--gradient-*`,
 * `--chart-4`), never hard-coded hex. Decorative: the canvas is `aria-hidden`.
 */
import { ContactShadows, Environment, Float, Lightformer, RoundedBox } from '@react-three/drei'
import { Canvas, useFrame } from '@react-three/fiber'
import * as React from 'react'
import * as THREE from 'three'

/** `--brand-500: 231 89.3% 66.5%` → a THREE.Color (sRGB). */
function tokenColor(name: string, fallback: string): THREE.Color {
  if (typeof window === 'undefined') return new THREE.Color(fallback)
  const raw = getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim()
  const parts = raw.split(/\s+/)
  if (parts.length !== 3) return new THREE.Color(fallback)
  return new THREE.Color(`hsl(${parts[0]}, ${parts[1]}, ${parts[2]})`)
}

interface Palette {
  paper: THREE.Color
  ink: THREE.Color
  heading: THREE.Color
  line: THREE.Color
  lineSoft: THREE.Color
  chip: THREE.Color
  indigo: THREE.Color
  violet: THREE.Color
  warm: THREE.Color
  shadow: THREE.Color
}

function usePalette(): Palette {
  return React.useMemo(
    () => ({
      paper: tokenColor('hero-foreground', '#f9fafe'),
      ink: tokenColor('brand-800', '#2d3897'),
      heading: tokenColor('brand-500', '#5d74f6'),
      line: tokenColor('brand-200', '#ccd8fe'),
      lineSoft: tokenColor('brand-100', '#e4eaff'),
      chip: tokenColor('brand-100', '#e4eaff'),
      indigo: tokenColor('gradient-from', '#4150d7'),
      violet: tokenColor('gradient-via', '#7335d0'),
      warm: tokenColor('chart-4', '#eda100'),
      shadow: tokenColor('brand-950', '#141c46'),
    }),
    [],
  )
}

/* ------------------------------------------------------------------ motion helpers */

/**
 * Staggered spring entrance: rises from `offset` below and settles with a little overshoot.
 * Integrated per frame (stiffness / damping), transform-only.
 */
function useSpringEntrance(delay: number, offset = 0.45) {
  const ref = React.useRef<THREE.Group>(null)
  const state = React.useRef({ y: -offset, v: 0, s: 0.9, sv: 0, t: 0 })
  useFrame((_, rawDelta) => {
    const group = ref.current
    if (!group) return
    const delta = Math.min(rawDelta, 1 / 30)
    const st = state.current
    st.t += delta
    if (st.t < delay) {
      group.position.y = st.y
      group.scale.setScalar(st.s)
      return
    }
    const k = 70
    const c = 11
    st.v += (-k * st.y - c * st.v) * delta
    st.y += st.v * delta
    st.sv += (-k * (st.s - 1) - c * st.sv) * delta
    st.s += st.sv * delta
    group.position.y = st.y
    group.scale.setScalar(st.s)
  })
  return ref
}

/** Leans the whole composition towards the pointer, eased, at most ±6°. */
function Parallax({ children }: { children: React.ReactNode }) {
  const ref = React.useRef<THREE.Group>(null)
  const max = THREE.MathUtils.degToRad(6)
  useFrame((state, delta) => {
    const group = ref.current
    if (!group) return
    group.rotation.y = THREE.MathUtils.damp(group.rotation.y, state.pointer.x * max, 3, delta)
    group.rotation.x = THREE.MathUtils.damp(group.rotation.x, -state.pointer.y * max, 3, delta)
  })
  return <group ref={ref}>{children}</group>
}

/* ------------------------------------------------------------------ objects */

function ResumeCard({ palette }: { palette: Palette }) {
  // [y, width, x, kind]  kind 0 = section heading, 1 = body line
  const lines: [number, number, number, 0 | 1][] = [
    [0.36, 0.62, -0.58, 0],
    [0.17, 1.58, -0.05, 1],
    [0.0, 1.36, -0.16, 1],
    [-0.17, 1.48, -0.1, 1],
    [-0.43, 0.7, -0.54, 0],
    [-0.62, 1.58, -0.05, 1],
    [-0.79, 1.2, -0.24, 1],
  ]
  return (
    <group>
      {/* The sheet: matte paper with a soft clearcoat. */}
      <RoundedBox args={[2.2, 2.9, 0.12]} radius={0.12} smoothness={6}>
        <meshPhysicalMaterial color={palette.paper} roughness={0.5} clearcoat={0.35} clearcoatRoughness={0.4} />
      </RoundedBox>

      {/* Photo chip + name and title lines. */}
      <mesh position={[-0.66, 1.0, 0.075]} rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[0.24, 0.24, 0.05, 48]} />
        <meshPhysicalMaterial color={palette.violet} roughness={0.35} clearcoat={0.8} clearcoatRoughness={0.25} />
      </mesh>
      <RoundedBox args={[1.0, 0.12, 0.04]} radius={0.05} smoothness={4} position={[0.13, 1.08, 0.07]}>
        <meshPhysicalMaterial color={palette.ink} roughness={0.45} />
      </RoundedBox>
      <RoundedBox args={[0.7, 0.08, 0.03]} radius={0.035} smoothness={4} position={[-0.02, 0.88, 0.065]}>
        <meshPhysicalMaterial color={palette.line} roughness={0.55} />
      </RoundedBox>

      {/* Extruded content lines. */}
      {lines.map(([y, width, x, kind], index) => (
        <RoundedBox
          key={index}
          args={[width, kind === 0 ? 0.09 : 0.065, kind === 0 ? 0.04 : 0.03]}
          radius={0.03}
          smoothness={4}
          position={[x, y, 0.07]}
        >
          <meshPhysicalMaterial color={kind === 0 ? palette.heading : palette.line} roughness={0.5} />
        </RoundedBox>
      ))}

      {/* Skill pills. */}
      {[-0.62, -0.12, 0.38].map((x, index) => (
        <RoundedBox key={x} args={[index === 2 ? 0.36 : 0.44, 0.16, 0.05]} radius={0.075} smoothness={4} position={[x, -1.1, 0.075]}>
          <meshPhysicalMaterial color={palette.chip} roughness={0.5} />
        </RoundedBox>
      ))}
    </group>
  )
}

/** Floating "match" chip: white pill, a track ring and a warm score arc, two text lines. */
function MatchChip({ palette }: { palette: Palette }) {
  return (
    <group>
      <RoundedBox args={[1.5, 0.66, 0.14]} radius={0.2} smoothness={6}>
        <meshPhysicalMaterial color={palette.paper} roughness={0.42} clearcoat={0.6} clearcoatRoughness={0.3} />
      </RoundedBox>
      <mesh position={[-0.44, 0, 0.08]}>
        <torusGeometry args={[0.18, 0.045, 24, 64]} />
        <meshPhysicalMaterial color={palette.lineSoft} roughness={0.5} />
      </mesh>
      <mesh position={[-0.44, 0, 0.1]} rotation={[0, 0, Math.PI / 2]}>
        <torusGeometry args={[0.18, 0.05, 24, 64, Math.PI * 1.55]} />
        <meshPhysicalMaterial color={palette.warm} roughness={0.32} clearcoat={0.8} clearcoatRoughness={0.2} />
      </mesh>
      <RoundedBox args={[0.6, 0.09, 0.03]} radius={0.04} smoothness={4} position={[0.22, 0.09, 0.08]}>
        <meshPhysicalMaterial color={palette.ink} roughness={0.45} />
      </RoundedBox>
      <RoundedBox args={[0.42, 0.07, 0.03]} radius={0.03} smoothness={4} position={[0.13, -0.1, 0.08]}>
        <meshPhysicalMaterial color={palette.line} roughness={0.55} />
      </RoundedBox>
    </group>
  )
}

/** Check badge: a glossy indigo disc with an extruded white tick. */
function CheckBadge({ palette }: { palette: Palette }) {
  return (
    <group>
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[0.4, 0.4, 0.14, 64]} />
        <meshPhysicalMaterial color={palette.indigo} roughness={0.3} clearcoat={1} clearcoatRoughness={0.18} />
      </mesh>
      <group position={[0, -0.02, 0.09]}>
        <RoundedBox args={[0.2, 0.075, 0.05]} radius={0.035} smoothness={4} position={[-0.1, -0.02, 0]} rotation={[0, 0, -Math.PI / 4]}>
          <meshPhysicalMaterial color={palette.paper} roughness={0.4} />
        </RoundedBox>
        <RoundedBox args={[0.38, 0.075, 0.05]} radius={0.035} smoothness={4} position={[0.08, 0.06, 0]} rotation={[0, 0, Math.PI / 3.6]}>
          <meshPhysicalMaterial color={palette.paper} roughness={0.4} />
        </RoundedBox>
      </group>
    </group>
  )
}

function Composition() {
  const palette = usePalette()
  const card = useSpringEntrance(0.05)
  const chip = useSpringEntrance(0.25)
  const badge = useSpringEntrance(0.4)
  return (
    <Parallax>
      <group ref={card}>
        <Float speed={1.1} rotationIntensity={0.18} floatIntensity={0.35} floatingRange={[-0.05, 0.05]}>
          <group rotation={[0.06, -0.3, 0.035]}>
            <ResumeCard palette={palette} />
          </group>
        </Float>
      </group>

      <group ref={chip}>
        <Float speed={1.5} rotationIntensity={0.25} floatIntensity={0.6} floatingRange={[-0.07, 0.07]}>
          <group position={[1.32, 1.36, 0.8]} rotation={[0.05, -0.34, 0.04]}>
            <MatchChip palette={palette} />
          </group>
        </Float>
      </group>

      <group ref={badge}>
        <Float speed={1.7} rotationIntensity={0.3} floatIntensity={0.7} floatingRange={[-0.06, 0.06]}>
          <group position={[-1.38, -1.05, 0.9]} rotation={[0.12, 0.35, -0.08]}>
            <CheckBadge palette={palette} />
          </group>
        </Float>
      </group>

      <ContactShadows position={[0, -1.85, 0]} opacity={0.32} scale={7} blur={2.8} far={3.2} resolution={512} color={palette.shadow} />
    </Parallax>
  )
}

export interface HeroSceneProps {
  /** Fired once the first frame has rendered (the static fallback can fade out). */
  onReady?: () => void
  className?: string
}

export default function HeroScene({ onReady, className }: HeroSceneProps) {
  return (
    <Canvas
      className={className}
      aria-hidden
      dpr={[1, 1.75]}
      camera={{ position: [0, 0.05, 8.4], fov: 34 }}
      gl={{ antialias: true, alpha: true, powerPreference: 'low-power', preserveDrawingBuffer: false }}
      onCreated={({ gl }) => {
        gl.toneMapping = THREE.NeutralToneMapping
        gl.toneMappingExposure = 1.0
        requestAnimationFrame(() => onReady?.())
      }}
    >
      <ambientLight intensity={0.6} />
      <directionalLight position={[2.5, 4, 5]} intensity={1.5} />
      {/* Procedural studio for reflections: soft key, rim and fill panels (no HDR fetch). */}
      <Environment resolution={256} frames={1}>
        <Lightformer form="rect" intensity={2.4} position={[0, 4, 4]} scale={[8, 3, 1]} />
        <Lightformer form="rect" intensity={1.8} position={[0, 0.5, 7]} scale={[7, 5, 1]} />
        <Lightformer form="rect" intensity={1.2} position={[-5, 1, 2]} rotation-y={Math.PI / 2} scale={[6, 4, 1]} />
        <Lightformer form="rect" intensity={1.6} position={[5, 0, 1]} rotation-y={-Math.PI / 2} scale={[6, 4, 1]} />
        <Lightformer form="circle" intensity={1.4} position={[0, -3, 3]} scale={3} />
      </Environment>
      <Composition />
    </Canvas>
  )
}
