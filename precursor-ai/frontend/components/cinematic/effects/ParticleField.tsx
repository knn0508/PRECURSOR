"use client";

import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import { AdditiveBlending, BufferAttribute, BufferGeometry, Points, ShaderMaterial, Vector3 } from "three";
import { PARTICLE_FRAG, PARTICLE_VERT } from "../shaders/radar";
import type { SatState } from "../scenes/SatelliteScene";

/** One draw call: particles stream from the satellite to the ground footprint (animated in the vertex shader). */
export function ParticleField({ state, count }: { state: SatState; count: number }) {
  const ref = useRef<Points>(null);
  const { geo, mat } = useMemo(() => {
    const g = new BufferGeometry();
    g.setAttribute("position", new BufferAttribute(new Float32Array(count * 3), 3)); // unused, required by Points
    const seed = new Float32Array(count);
    const jit = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      seed[i] = Math.random();
      jit[i * 3] = (Math.random() - 0.5) * 2;
      jit[i * 3 + 1] = (Math.random() - 0.5) * 2;
      jit[i * 3 + 2] = (Math.random() - 0.5) * 2;
    }
    g.setAttribute("aSeed", new BufferAttribute(seed, 1));
    g.setAttribute("aJitter", new BufferAttribute(jit, 3));
    return {
      geo: g,
      mat: new ShaderMaterial({
        vertexShader: PARTICLE_VERT,
        fragmentShader: PARTICLE_FRAG,
        uniforms: {
          uTime: { value: 0 },
          uSpeed: { value: 0.3 },
          uSize: { value: 3.5 },
          uIntensity: { value: 0 },
          uFrom: { value: new Vector3() },
          uTo: { value: new Vector3() },
        },
        transparent: true,
        depthWrite: false,
        blending: AdditiveBlending,
      }),
    };
  }, [count]);
  useEffect(
    () => () => {
      geo.dispose();
      mat.dispose();
    },
    [geo, mat],
  );

  useFrame(({ clock }) => {
    const pts = ref.current;
    if (!pts) return;
    pts.visible = state.vis > 0.02;
    if (!pts.visible) return;
    mat.uniforms.uTime.value = clock.elapsedTime;
    mat.uniforms.uIntensity.value = state.vis;
    mat.uniforms.uFrom.value.copy(state.pos);
    mat.uniforms.uTo.value.copy(state.target);
  });

  return <points ref={ref} geometry={geo} material={mat} frustumCulled={false} />;
}
