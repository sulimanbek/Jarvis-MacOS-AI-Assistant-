import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import type { Drive } from './Scene'

/**
 * Warp speed, for the moments Jarvis is thinking or working.
 *
 * Streaks of light rush outward from behind the reactor to the edges of the
 * frame, long and fast while he works and gone when he answers. They are drawn
 * in screen space rather than in the 3D scene: a streak is a line from a point
 * on the ring's rim to somewhere near the edge, and doing it as flat quads
 * keeps every streak a clean, crisp line of constant width at any resolution.
 *
 * Each streak is one instanced quad. Its position is a pure function of a
 * single phase that advances with the warp amount, so speeding up, slowing
 * down and stopping all stay smooth and nothing has to be reset.
 */

const COUNT = 900

const vertex = /* glsl */ `
  uniform float uPhase;
  uniform float uWarp;
  uniform float uLen;
  uniform float uAspect;
  uniform float uHeightCss;
  uniform float uRmax;
  uniform vec3 uTint;

  attribute float aAngle;
  attribute float aR0;
  attribute float aSpeed;
  attribute float aWidth;
  attribute float aLenScale;
  attribute float aBright;
  attribute float aTemp;

  varying float vA;
  varying float vAlong;
  varying float vAcross;
  varying vec3 vCol;

  void main() {
    // Where this streak is on its journey, 0 at birth and 1 at the edge.
    float t = fract(aR0 + uPhase * aSpeed);
    float e = pow(t, 1.7); // accelerating, so it reads as rushing toward you

    // Units: half the screen height is 1. The ring's rim is at about 0.6, so
    // streaks are born just behind it and never cross the inside of the ring.
    float r = mix(0.46, uRmax, e);
    vec2 dir = vec2(cos(aAngle), sin(aAngle));

    // Longer the further out, like real perspective streaks.
    float len = uLen * aLenScale * (0.10 + r * 0.9);
    float tail = max(r - len, 0.40);
    float rr = mix(tail, r, position.y);

    vec2 perp = vec2(-dir.y, dir.x);
    float w = aWidth * 2.0 / uHeightCss;
    vec2 p = dir * rr + perp * position.x * w;
    gl_Position = vec4(p.x / uAspect, p.y, 0.0, 1.0);

    float fadeIn = smoothstep(0.0, 0.12, t);
    float fadeOut = 1.0 - smoothstep(0.86, 1.0, t);
    vA = uWarp * aBright * fadeIn * fadeOut;

    vAlong = position.y;
    vAcross = position.x * 2.0;
    vec3 base = mix(vec3(0.62, 0.78, 1.0), vec3(1.0), aTemp);
    vCol = mix(base, uTint, 0.25);
  }
`

const fragment = /* glsl */ `
  varying float vA;
  varying float vAlong;
  varying float vAcross;
  varying vec3 vCol;

  void main() {
    // Soft across the width, dim at the tail and bright at the head.
    float across = 1.0 - smoothstep(0.0, 1.0, abs(vAcross));
    float head = pow(vAlong, 1.6);
    float a = vA * across * across * head;
    if (a < 0.002) discard;
    gl_FragColor = vec4(vCol * a * 1.4, a);
  }
`

export function WarpStreaks({ drive }: { drive: Drive }) {
  const mat = useRef<THREE.ShaderMaterial>(null)
  const phase = useRef(0)

  const geometry = useMemo(() => {
    let seed = 90210
    const rand = () => {
      seed = (seed * 1664525 + 1013904223) >>> 0
      return seed / 4294967296
    }

    const g = new THREE.InstancedBufferGeometry()
    // A unit quad: x across the width, y from tail (0) to head (1).
    g.setAttribute(
      'position',
      new THREE.BufferAttribute(new Float32Array([-0.5, 0, 0, 0.5, 0, 0, 0.5, 1, 0, -0.5, 1, 0]), 3),
    )
    g.setIndex([0, 1, 2, 0, 2, 3])

    const angle = new Float32Array(COUNT)
    const r0 = new Float32Array(COUNT)
    const speed = new Float32Array(COUNT)
    const width = new Float32Array(COUNT)
    const lenScale = new Float32Array(COUNT)
    const bright = new Float32Array(COUNT)
    const temp = new Float32Array(COUNT)
    for (let i = 0; i < COUNT; i++) {
      angle[i] = rand() * Math.PI * 2
      r0[i] = rand()
      speed[i] = 0.6 + rand() * 0.9
      // Mostly thin and faint, a few bold ones.
      const m = Math.pow(rand(), 2.2)
      width[i] = 1.1 + m * 2.4
      lenScale[i] = 0.55 + rand() * 0.9
      bright[i] = 0.22 + m * 0.78
      temp[i] = rand()
    }
    const inst = (a: Float32Array) => new THREE.InstancedBufferAttribute(a, 1)
    g.setAttribute('aAngle', inst(angle))
    g.setAttribute('aR0', inst(r0))
    g.setAttribute('aSpeed', inst(speed))
    g.setAttribute('aWidth', inst(width))
    g.setAttribute('aLenScale', inst(lenScale))
    g.setAttribute('aBright', inst(bright))
    g.setAttribute('aTemp', inst(temp))
    g.instanceCount = COUNT
    return g
  }, [])

  const uniforms = useMemo(
    () => ({
      uPhase: { value: 0 },
      uWarp: { value: 0 },
      uLen: { value: 0 },
      uAspect: { value: 1.6 },
      uHeightCss: { value: 900 },
      uRmax: { value: 1.9 },
      uTint: { value: new THREE.Color('#4f8cff') },
    }),
    [],
  )

  useFrame((state, dt) => {
    const m = mat.current
    if (!m) return
    const u = m.uniforms
    const w = drive.warp

    // The phase only moves while there is warp, and moves faster the more
    // there is, so streaks accelerate in and coast out.
    phase.current += dt * (0.12 + 0.7 * w)

    const { width, height } = state.size
    const aspect = width / height
    u.uPhase.value = phase.current
    u.uWarp.value = w
    u.uLen.value = 0.6 * w
    u.uAspect.value = aspect
    // Lines keep their proportions from a laptop to a 4K monitor at 100%.
    u.uHeightCss.value = height / THREE.MathUtils.clamp(height / 900, 0.8, 2.6)
    u.uRmax.value = Math.sqrt(aspect * aspect + 1) + 0.1
    ;(u.uTint.value as THREE.Color).lerp(drive.color, Math.min(1, dt * 2))

    // Nothing to draw, nothing to pay for.
    if (m.visible !== w > 0.004) m.visible = w > 0.004
  })

  return (
    <mesh renderOrder={-1} frustumCulled={false} geometry={geometry}>
      <shaderMaterial
        ref={mat}
        uniforms={uniforms}
        vertexShader={vertex}
        fragmentShader={fragment}
        transparent
        blending={THREE.AdditiveBlending}
        depthWrite={false}
        depthTest={false}
        side={THREE.DoubleSide}
      />
    </mesh>
  )
}
