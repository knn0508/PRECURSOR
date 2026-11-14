"use client";

import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import type { Group } from "three";
import { progress } from "../animations/progress";
import { DeformationLayer } from "../effects/DeformationLayer";
import { RiskHeatmap } from "../effects/RiskHeatmap";
import { TerrainModel } from "../objects/TerrainModel";
import { createTerrainUniforms } from "../shaders/terrain";
import { smooth } from "../utils/math";
import { buildTerrainGeometry } from "../utils/terrain";

/** Terrain patch in the Earth-local frame (x east, y up, z south). Scroll drives all stage uniforms. */
export function TerrainScene({ segments }: { segments: number }) {
  const group = useRef<Group>(null);
  const uniforms = useMemo(() => createTerrainUniforms(), []);
  const geometry = useMemo(() => buildTerrainGeometry(segments), [segments]);
  useEffect(() => () => geometry.dispose(), [geometry]);

  useFrame(({ clock }) => {
    const p = progress.p;
    const t = clock.elapsedTime;
    uniforms.uTime.value = t;
    uniforms.uAppear.value = smooth(0.33, 0.38, p); // surface becomes radar data
    uniforms.uSar.value = smooth(0.34, 0.42, p); // SAR amplitude raster + grid + scan
    uniforms.uInsar.value = smooth(0.43, 0.52, p) * (1 - smooth(0.56, 0.62, p)); // interferogram fringes
    uniforms.uRelief.value = smooth(0.52, 0.62, p); // flat raster -> 3D relief
    uniforms.uTopo.value = smooth(0.55, 0.63, p); // elevation model + contours
    uniforms.uRisk.value = smooth(0.62, 0.76, p); // risk heatmap emerges
    uniforms.uDeform.value = 0.2 * smooth(0.56, 0.78, p); // animated displacement (exaggerated)
    uniforms.uFlat.value = smooth(0.84, 0.95, p); // relief flattens into map view
    uniforms.uScan.value = -2.6 + 5.2 * ((t * 0.25) % 1);
    if (group.current) group.current.visible = uniforms.uAppear.value > 0.001;
  });

  return (
    <group ref={group} visible={false}>
      <TerrainModel geometry={geometry} uniforms={uniforms} />
      <RiskHeatmap geometry={geometry} uniforms={uniforms} />
      <DeformationLayer />
    </group>
  );
}
