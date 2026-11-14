"use client";

import { Stars } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import type { Group } from "three";
import { progress } from "../animations/progress";

/** Far background layer. Barely rotates with scroll, so it reads as distant against the moving camera. */
export function Starfield({ count }: { count: number }) {
  const ref = useRef<Group>(null);
  useFrame(() => {
    if (ref.current) ref.current.rotation.y = progress.p * 0.12;
  });
  return (
    <group ref={ref}>
      <Stars radius={180} depth={60} count={count} factor={4} saturation={0} fade speed={0.2} />
    </group>
  );
}
