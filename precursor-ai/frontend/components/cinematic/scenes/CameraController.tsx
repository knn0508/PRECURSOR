"use client";

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { PerspectiveCamera, Vector3 } from "three";
import { progress } from "../animations/progress";
import { sampleCamera } from "../animations/cameraPath";

/** Applies the scroll-driven camera path plus a small pointer parallax (desktop only). */
export function CameraController({ mobile }: { mobile: boolean }) {
  const pos = useMemo(() => new Vector3(), []);
  const look = useMemo(() => new Vector3(), []);
  const pointer = useRef({ x: 0, y: 0 });

  useFrame(({ camera, pointer: target, size }, dt) => {
    sampleCamera(progress.p, pos, look);

    // Portrait screens: pull back and widen the FOV so the subject still fits.
    const aspect = size.width / size.height;
    const k = aspect < 0.9 ? 1 + (0.9 - aspect) * 1.3 : 1;
    pos.sub(look).multiplyScalar(k).add(look);
    const cam = camera as PerspectiveCamera;
    const fov = aspect < 0.9 ? 52 : 42;
    if (cam.fov !== fov) {
      cam.fov = fov;
      cam.updateProjectionMatrix();
    }

    if (!mobile) {
      const s = pointer.current;
      const a = Math.min(1, dt * 2);
      s.x += (target.x - s.x) * a;
      s.y += (target.y - s.y) * a;
      const d = pos.distanceTo(look);
      pos.x += s.x * d * 0.02;
      pos.y += s.y * d * 0.012;
    }

    cam.position.copy(pos);
    cam.lookAt(look);
  });

  return null;
}
