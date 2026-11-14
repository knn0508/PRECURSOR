"use client";

import { Line } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { Vector3 } from "three";
import { progress } from "../animations/progress";
import { ORBIT_R, orbitPoint } from "../utils/geo";
import { smooth } from "../utils/math";

export function SatelliteOrbit({ segments = 256 }: { segments?: number }) {
  const ref = useRef<{ material: { opacity: number }; visible: boolean }>(null);
  const points = useMemo(
    () => Array.from({ length: segments + 1 }, (_, i) => orbitPoint((i / segments) * Math.PI * 2, ORBIT_R, new Vector3())),
    [segments],
  );

  useFrame(() => {
    if (!ref.current) return;
    const p = progress.p;
    const o = smooth(0.08, 0.16, p) * (1 - smooth(0.38, 0.46, p));
    ref.current.material.opacity = 0.4 * o;
    ref.current.visible = o > 0.01;
  });

  // @ts-expect-error drei Line ref is a Line2; only opacity/visible are touched here.
  return <Line ref={ref} points={points} color="#38bdf8" lineWidth={1} transparent opacity={0} depthWrite={false} />;
}
