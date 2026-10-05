import { useMemo, useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import type { Drive } from './Scene'

/**
 * The space behind the reactor: a sharp starfield over a faint Milky Way.
 *
 * It replaces the old particle shell, which was a few thousand large soft discs
 * orbiting the core and read as bokeh rather than sky. What makes this read as
 * real is mostly restraint:
 *
 *   - Sizes are in physical pixels (css size x device pixel ratio), so a star
 *     is as crisp on a 4K panel as on a laptop. Faint stars are 1-2 css px.
 *   - Brightness follows a steep power law: thousands you barely see, a few
 *     hundred you notice, a dozen "hero" stars with a soft halo and spikes.
 *   - Colour follows temperature — blue-white through white to warm — nudged a
 *     little toward the interface blue so it sits in the same world.
 *   - Stars are infinitely far, so size does not change with depth. Depth is
 *     carried by parallax: nearer layers slide further against the camera drift.
 *   - The band of light is domain-warped noise with dust lanes cut through it,
 *     and the output is dithered so the dark gradients do not band on big,
 *     high-bit-depth displays.
 *
 * Everything is generated from a fixed seed, so the sky is the same every load.
 */

const STARS = 7600
const HERO = 14

/** The galactic plane's normal. Chosen so the band crosses the frame diagonally,
 *  a little below centre, rather than running straight behind the reactor. */
const BAND = new THREE.Vector3(0.55, -0.8, 0.15).normalize()

/** Small, fast, good-enough seeded generator (mulberry32). */
function rng(seed: number) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const starVertex = /* glsl */ `
  uniform float uTime;
  uniform float uLevel;
  uniform float uPx;
  uniform float uTwinkle;
  uniform vec2 uCam;
  uniform vec3 uTint;

  attribute float aSeed;
  attribute float aSize;
  attribute float aBright;
  attribute float aTw;
  attribute float aTemp;
  attribute float aLayer;
  attribute float aSpike;

  varying float vB;
  varying vec3 vCol;
  varying float vSpike;
  varying float vSize;

  void main() {
    vec3 p = position;
    // Parallax: nearer layers slide further against the camera's slow drift.
    p.xy -= uCam * aLayer * 3.0;

    gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);

    // Slow scintillation, a different rate and phase for every star.
    float tw = 1.0 - uTwinkle * aTw *
      (0.5 + 0.5 * sin(uTime * (0.7 + aSeed * 2.1) + aSeed * 40.0));
    vB = aBright * tw * (1.0 + uLevel * 0.5);

    // Colour temperature: cool blue-white -> white -> warm.
    vec3 cool = vec3(0.62, 0.78, 1.0);
    vec3 warm = vec3(1.0, 0.86, 0.68);
    vec3 c = aTemp < 0.6
      ? mix(cool, vec3(1.0), aTemp / 0.6)
      : mix(vec3(1.0), warm, (aTemp - 0.6) / 0.4);
    vCol = mix(c, uTint, 0.18);

    vSpike = aSpike;
    // Physical pixels, so the field is equally sharp at any pixel ratio.
    gl_PointSize = aSize * uPx;
    vSize = gl_PointSize;
  }
`

const starFragment = /* glsl */ `
  varying float vB;
  varying vec3 vCol;
  varying float vSpike;
  varying float vSize;

  void main() {
    vec2 d = (gl_PointCoord - 0.5) * 2.0;
    float r2 = dot(d, d);

    // A gaussian core, so a point stays a point. Its width has to follow the
    // sprite: on a 2-pixel sprite the pixel centres sit half-way to the edge,
    // and a tight falloff there leaves the whole star black.
    float k = mix(1.6, 22.0, clamp((vSize - 2.5) / 9.0, 0.0, 1.0));
    float core = exp(-r2 * k);
    float halo = exp(-sqrt(r2) * 5.0) * 0.18;

    // Diffraction spikes — only the hero stars carry any.
    float h = exp(-abs(d.y) * 70.0) * exp(-abs(d.x) * 5.5);
    float v = exp(-abs(d.x) * 70.0) * exp(-abs(d.y) * 5.5);
    float spike = (h + v) * vSpike * 0.8;

    float a = (core + halo * (0.4 + vSpike) + spike) * vB;
    if (a < 0.003) discard;
    gl_FragColor = vec4(vCol * a, a);
  }
`

const nebulaVertex = /* glsl */ `
  varying vec3 vDir;
  void main() {
    vDir = normalize(position);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`

const nebulaFragment = /* glsl */ `
  uniform float uTime;
  uniform float uLevel;
  uniform vec3 uBand;
  uniform vec3 uTint;
  varying vec3 vDir;

  float hash(vec3 p) {
    p = fract(p * 0.3183099 + 0.1);
    p *= 17.0;
    return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
  }

  float noise(vec3 x) {
    vec3 i = floor(x);
    vec3 f = fract(x);
    f = f * f * (3.0 - 2.0 * f);
    return mix(
      mix(mix(hash(i + vec3(0, 0, 0)), hash(i + vec3(1, 0, 0)), f.x),
          mix(hash(i + vec3(0, 1, 0)), hash(i + vec3(1, 1, 0)), f.x), f.y),
      mix(mix(hash(i + vec3(0, 0, 1)), hash(i + vec3(1, 0, 1)), f.x),
          mix(hash(i + vec3(0, 1, 1)), hash(i + vec3(1, 1, 1)), f.x), f.y),
      f.z);
  }

  float fbm(vec3 p) {
    float a = 0.5;
    float s = 0.0;
    for (int i = 0; i < 5; i++) {
      s += a * noise(p);
      p = p * 2.03 + vec3(1.7, 9.2, 3.1);
      a *= 0.5;
    }
    return s;
  }

  void main() {
    vec3 dir = normalize(vDir);

    // Domain warp: bends the noise into the filaments real nebulae have,
    // instead of the round clouds plain fbm gives.
    vec3 q = dir * 2.0;
    q += 0.65 * vec3(fbm(q + 3.1), fbm(q + 7.7), fbm(q + 1.3));
    float n = fbm(q * 1.5 + uTime * 0.003);

    float b = dot(dir, uBand);
    float band = exp(-b * b * 15.0);

    float dens = band * smoothstep(0.30, 0.95, n);
    // Dark dust lanes cut through the bright band.
    float lane = fbm(q * 3.0 + 11.0);
    dens *= 1.0 - 0.7 * smoothstep(0.55, 0.78, lane);

    // A very faint wide haze, so the sky is never flat black.
    float haze = 0.30 * fbm(dir * 1.2 + 5.0) * exp(-b * b * 2.5);

    vec3 navy = vec3(0.004, 0.010, 0.035);
    vec3 deep = vec3(0.025, 0.070, 0.28);
    vec3 glow = vec3(0.17, 0.34, 0.92);
    vec3 col = navy * haze * 3.0;
    col += mix(deep, glow, dens) * dens * 0.5;
    // A hint of violet at the densest edges.
    col += vec3(0.22, 0.10, 0.40) * dens * dens * 0.14;

    // Lean a touch toward the current accent, so the sky follows the mood.
    float m = max(max(uTint.r, uTint.g), max(uTint.b, 0.001));
    col *= mix(vec3(1.0), uTint / m, 0.22);
    col *= 1.0 + uLevel * 0.25;

    // Dither, about one to two 8-bit steps, so dark gradients do not band.
    col += (hash(vec3(gl_FragCoord.xy, 7.0)) - 0.5) * (1.5 / 255.0);

    gl_FragColor = vec4(max(col, 0.0), 1.0);
  }
`

export function Starfield({ drive }: { drive: Drive }) {
  const group = useRef<THREE.Group>(null)
  const starMat = useRef<THREE.ShaderMaterial>(null)
  const nebMat = useRef<THREE.ShaderMaterial>(null)
  const gl = useThree((s) => s.gl)

  const stars = useMemo(() => {
    const rand = rng(20260105)
    const n = STARS + HERO
    const position = new Float32Array(n * 3)
    const seed = new Float32Array(n)
    const size = new Float32Array(n)
    const bright = new Float32Array(n)
    const tw = new Float32Array(n)
    const temp = new Float32Array(n)
    const layer = new Float32Array(n)
    const spike = new Float32Array(n)

    const direction = (clustered: boolean) => {
      for (;;) {
        const u = rand() * 2 - 1
        const th = rand() * Math.PI * 2
        const r = Math.sqrt(1 - u * u)
        const x = Math.cos(th) * r
        const y = u
        const z = Math.sin(th) * r
        if (!clustered) return [x, y, z] as const
        // Rejection sampling toward the galactic plane.
        const b = x * BAND.x + y * BAND.y + z * BAND.z
        if (rand() < Math.exp(-b * b * 12.0)) return [x, y, z] as const
      }
    }

    for (let i = 0; i < n; i++) {
      const hero = i >= STARS
      // Roughly 45% of the field piles up along the Milky Way.
      const [x, y, z] = direction(!hero && rand() < 0.45)
      const radius = 40 + rand() * 60
      position[i * 3] = x * radius
      position[i * 3 + 1] = y * radius
      position[i * 3 + 2] = z * radius

      seed[i] = rand()
      tw[i] = 0.25 + rand() * 0.75

      // Colour temperature: mostly blue-white and white, a few warm ones.
      const t = rand()
      temp[i] = t < 0.55 ? t * 0.8 : t < 0.9 ? 0.45 + (t - 0.55) * 0.9 : 0.8 + (t - 0.9) * 2

      if (hero) {
        size[i] = 20 + rand() * 14
        bright[i] = 0.85 + rand() * 0.15
        spike[i] = 1
        layer[i] = 1
      } else {
        // Steep power law: most stars are faint and tiny.
        const m = Math.pow(rand(), 3.2)
        size[i] = 1.5 + m * 3.6
        bright[i] = 0.34 + Math.pow(m, 0.6) * 0.66
        spike[i] = 0
        layer[i] = m > 0.35 ? 1 : m > 0.08 ? 0.5 : 0.1
      }
    }
    return { position, seed, size, bright, tw, temp, layer, spike }
  }, [])

  const starUniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uLevel: { value: 0 },
      uPx: { value: 1 },
      uTwinkle: { value: 0.28 },
      uCam: { value: new THREE.Vector2() },
      uTint: { value: new THREE.Color('#4f8cff') },
    }),
    [],
  )

  const nebUniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uLevel: { value: 0 },
      uBand: { value: BAND.clone() },
      uTint: { value: new THREE.Color('#4f8cff') },
    }),
    [],
  )

  useFrame((state, dt) => {
    const t = state.clock.elapsedTime
    const s = starMat.current?.uniforms
    const nb = nebMat.current?.uniforms
    if (!s || !nb) return

    s.uTime.value = t
    // Physical pixels, scaled with the viewport's height, so the sky has the same
    // proportions on a laptop and on a 4K monitor running at 100%.
    s.uPx.value = gl.getPixelRatio() * THREE.MathUtils.clamp(state.size.height / 900, 0.8, 2.6)
    s.uLevel.value += (drive.level - s.uLevel.value) * Math.min(1, dt * 6)
    ;(s.uCam.value as THREE.Vector2).set(state.camera.position.x, state.camera.position.y)
    ;(s.uTint.value as THREE.Color).lerp(drive.color, Math.min(1, dt * 2))

    nb.uTime.value = t
    nb.uLevel.value = s.uLevel.value
    ;(nb.uTint.value as THREE.Color).copy(s.uTint.value as THREE.Color)

    // A few degrees of slow sway, in both directions, so the sky is alive but
    // never drifts away from where the band was composed.
    if (group.current) {
      group.current.rotation.z = Math.sin(t * 0.021) * 0.04
      group.current.rotation.y = Math.sin(t * 0.017) * 0.05
    }
  })

  return (
    <group ref={group}>
      {/* The band of light. A big sphere seen from inside, drawn first. */}
      <mesh renderOrder={-2} frustumCulled={false}>
        <sphereGeometry args={[150, 48, 32]} />
        <shaderMaterial
          ref={nebMat}
          uniforms={nebUniforms}
          vertexShader={nebulaVertex}
          fragmentShader={nebulaFragment}
          side={THREE.BackSide}
          depthWrite={false}
          depthTest={false}
        />
      </mesh>

      <points renderOrder={-1} frustumCulled={false}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[stars.position, 3]} />
          <bufferAttribute attach="attributes-aSeed" args={[stars.seed, 1]} />
          <bufferAttribute attach="attributes-aSize" args={[stars.size, 1]} />
          <bufferAttribute attach="attributes-aBright" args={[stars.bright, 1]} />
          <bufferAttribute attach="attributes-aTw" args={[stars.tw, 1]} />
          <bufferAttribute attach="attributes-aTemp" args={[stars.temp, 1]} />
          <bufferAttribute attach="attributes-aLayer" args={[stars.layer, 1]} />
          <bufferAttribute attach="attributes-aSpike" args={[stars.spike, 1]} />
        </bufferGeometry>
        <shaderMaterial
          ref={starMat}
          uniforms={starUniforms}
          vertexShader={starVertex}
          fragmentShader={starFragment}
          transparent
          blending={THREE.AdditiveBlending}
          depthWrite={false}
          depthTest={false}
        />
      </points>
    </group>
  )
}
