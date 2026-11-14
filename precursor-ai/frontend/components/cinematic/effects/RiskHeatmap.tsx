"use client";

import { useEffect, useMemo } from "react";
import { ShaderMaterial, type BufferGeometry } from "three";
import { HEAT_FRAG, TERRAIN_VERT, type TerrainUniforms } from "../shaders/terrain";

/** Illustrative relative-risk overlay draped on the terrain. Not a calibrated probability. */
export function RiskHeatmap({ geometry, uniforms }: { geometry: BufferGeometry; uniforms: TerrainUniforms }) {
  const mat = useMemo(
    () =>
      new ShaderMaterial({
        vertexShader: TERRAIN_VERT,
        fragmentShader: HEAT_FRAG,
        uniforms,
        transparent: true,
        depthWrite: false,
        polygonOffset: true,
        polygonOffsetFactor: -2,
        polygonOffsetUnits: -2,
      }),
    [uniforms],
  );
  useEffect(() => () => mat.dispose(), [mat]);
  return <mesh geometry={geometry} material={mat} frustumCulled={false} renderOrder={2} />;
}
