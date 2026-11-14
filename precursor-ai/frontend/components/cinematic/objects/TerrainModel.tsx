"use client";

import { useEffect, useMemo } from "react";
import { DoubleSide, ShaderMaterial, type BufferGeometry } from "three";
import { TERRAIN_FRAG, TERRAIN_VERT, type TerrainUniforms } from "../shaders/terrain";

/** Synthetic terrain mesh: SAR raster -> interferogram -> elevation model, all in one shader driven by uniforms. */
export function TerrainModel({ geometry, uniforms }: { geometry: BufferGeometry; uniforms: TerrainUniforms }) {
  const mat = useMemo(
    () =>
      new ShaderMaterial({
        vertexShader: TERRAIN_VERT,
        fragmentShader: TERRAIN_FRAG,
        uniforms,
        transparent: true,
        side: DoubleSide,
      }),
    [uniforms],
  );
  useEffect(() => () => mat.dispose(), [mat]);
  return <mesh geometry={geometry} material={mat} frustumCulled={false} />;
}
