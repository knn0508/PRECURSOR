"use client";

import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import { AdditiveBlending, DoubleSide, Mesh, PlaneGeometry, Quaternion, ShaderMaterial, Vector3 } from "three";
import { WAVES_FRAG, WAVES_VERT } from "../shaders/radar";
import type { SatState } from "../scenes/SatelliteScene";

const Z = new Vector3(0, 0, 1);

/** Pulsing rings on the ground footprint, tangent to the globe. */
export function RadarWaves({ state }: { state: SatState }) {
  const ref = useRef<Mesh>(null);
  const q = useMemo(() => new Quaternion(), []);
  const n = useMemo(() => new Vector3(), []);
  const { geo, mat } = useMemo(
    () => ({
      geo: new PlaneGeometry(3, 3),
      mat: new ShaderMaterial({
        vertexShader: WAVES_VERT,
        fragmentShader: WAVES_FRAG,
        uniforms: { uTime: { value: 0 }, uIntensity: { value: 0 } },
        transparent: true,
        depthWrite: false,
        blending: AdditiveBlending,
        side: DoubleSide,
      }),
    }),
    [],
  );
  useEffect(
    () => () => {
      geo.dispose();
      mat.dispose();
    },
    [geo, mat],
  );

  useFrame(({ clock }) => {
    const m = ref.current;
    if (!m) return;
    m.visible = state.vis > 0.02;
    if (!m.visible) return;
    n.copy(state.target).normalize();
    m.position.copy(state.target).addScaledVector(n, 0.03);
    m.quaternion.copy(q.setFromUnitVectors(Z, n));
    mat.uniforms.uTime.value = clock.elapsedTime;
    mat.uniforms.uIntensity.value = state.vis;
  });

  return <mesh ref={ref} geometry={geo} material={mat} frustumCulled={false} />;
}
