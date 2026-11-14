"use client";

import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import { AdditiveBlending, ConeGeometry, DoubleSide, Mesh, ShaderMaterial } from "three";
import { BEAM_FRAG, BEAM_VERT } from "../shaders/radar";
import type { SatState } from "../scenes/SatelliteScene";

/** Side-looking beam from the antenna to the ground footprint (artistic, not a measurement). */
export function RadarBeam({ state }: { state: SatState }) {
  const ref = useRef<Mesh>(null);
  const { geo, mat } = useMemo(() => {
    const g = new ConeGeometry(1, 1, 32, 1, true);
    g.translate(0, -0.5, 0); // apex at origin, base at y = -1
    g.rotateX(-Math.PI / 2); // axis -> +z (apex 0, base 1)
    return {
      geo: g,
      mat: new ShaderMaterial({
        vertexShader: BEAM_VERT,
        fragmentShader: BEAM_FRAG,
        uniforms: { uTime: { value: 0 }, uIntensity: { value: 0 } },
        transparent: true,
        depthWrite: false,
        blending: AdditiveBlending,
        side: DoubleSide,
      }),
    };
  }, []);
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
    const len = state.pos.distanceTo(state.target);
    m.position.copy(state.pos);
    m.lookAt(state.target);
    m.scale.set(len * 0.12, len * 0.12, len);
    mat.uniforms.uTime.value = clock.elapsedTime;
    mat.uniforms.uIntensity.value = state.vis;
  });

  return <mesh ref={ref} geometry={geo} material={mat} frustumCulled={false} />;
}
