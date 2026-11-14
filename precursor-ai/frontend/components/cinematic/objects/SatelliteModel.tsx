"use client";

import { forwardRef, useEffect, useMemo } from "react";
import { BoxGeometry, CylinderGeometry, Group, MeshStandardMaterial, SphereGeometry, DoubleSide } from "three";

/**
 * Procedural SAR-satellite stand-in (generic radar bus, NOT a model of a specific mission).
 * Local +z faces Earth (nadir); solar arrays extend along +/-x; the radar dish sits on a boom at +y.
 */
export const SatelliteModel = forwardRef<Group>(function SatelliteModel(_, ref) {
  const r = useMemo(
    () => ({
      bus: new BoxGeometry(0.6, 0.5, 0.8),
      panel: new BoxGeometry(1.1, 0.03, 0.7),
      frame: new BoxGeometry(1.14, 0.02, 0.04),
      boom: new CylinderGeometry(0.025, 0.025, 0.9, 8),
      dish: new SphereGeometry(1.0, 32, 12, 0, Math.PI * 2, 0, Math.PI / 3.2),
      gold: new MeshStandardMaterial({ color: "#c9b27a", metalness: 0.5, roughness: 0.4 }),
      cell: new MeshStandardMaterial({ color: "#10306b", metalness: 0.4, roughness: 0.35, emissive: "#06183a" }),
      metal: new MeshStandardMaterial({ color: "#aeb6c2", metalness: 0.6, roughness: 0.4 }),
      dishMat: new MeshStandardMaterial({ color: "#d9dde3", metalness: 0.3, roughness: 0.5, side: DoubleSide }),
    }),
    [],
  );

  useEffect(
    () => () => {
      Object.values(r).forEach((x) => x.dispose());
    },
    [r],
  );

  return (
    <group ref={ref}>
      <mesh geometry={r.bus} material={r.gold} />
      {[-1, 1].map((side) => (
        <group key={side} position={[side * 0.3, 0, 0]}>
          {[0, 1, 2].map((i) => (
            <group key={i} position={[side * (0.58 + i * 1.16), 0, 0]}>
              <mesh geometry={r.panel} material={r.cell} />
              <mesh geometry={r.frame} material={r.metal} position={[0, 0.02, 0.33]} />
              <mesh geometry={r.frame} material={r.metal} position={[0, 0.02, -0.33]} />
            </group>
          ))}
        </group>
      ))}
      <mesh geometry={r.boom} material={r.metal} position={[0, 0.65, 0.1]} />
      <mesh
        geometry={r.dish}
        material={r.dishMat}
        position={[0, 1.15, 0.1]}
        rotation={[Math.PI / 2, 0, 0]}
        scale={[1, 1, 0.55]}
      />
    </group>
  );
});
