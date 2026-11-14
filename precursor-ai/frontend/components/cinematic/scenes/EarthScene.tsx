"use client";

import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import type { Group } from "three";
import { progress } from "../animations/progress";
import { EarthAtmosphere, EarthGlobe } from "../objects/EarthGlobe";
import { PATCH_CENTER, PATCH_QUAT } from "../utils/geo";
import { smooth } from "../utils/math";
import { TerrainScene } from "./TerrainScene";

export function EarthScene({ mobile }: { mobile: boolean }) {
  const earth = useRef<Group>(null);
  const seg = mobile ? 64 : 128;

  useFrame(({ clock }) => {
    if (!earth.current) return;
    const p = progress.p;
    // Scroll-driven spin that settles to 0 (patch faces the camera approach), plus a slow idle drift that fades out.
    earth.current.rotation.y = 0.9 * (1 - smooth(0, 0.4, p)) + clock.elapsedTime * 0.04 * (1 - smooth(0.1, 0.3, p));
  });

  return (
    <>
      <group ref={earth}>
        <EarthGlobe segments={seg} />
        <group position={PATCH_CENTER} quaternion={PATCH_QUAT}>
          <TerrainScene segments={mobile ? 72 : 140} />
        </group>
      </group>
      <EarthAtmosphere segments={seg} />
    </>
  );
}
