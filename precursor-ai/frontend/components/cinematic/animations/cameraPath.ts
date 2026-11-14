import { Vector3 } from "three";
import { patchPoint } from "../utils/geo";
import { HOT } from "../utils/terrain";
import { clamp01 } from "../utils/math";

export interface CameraKey {
  p: number;
  pos: Vector3;
  look: Vector3;
}

const hot = (up: number) => patchPoint(HOT.x * 0.5, up, HOT.z * 0.5);

/**
 * One continuous camera journey. Chapter boundaries (0.15 / 0.35 / 0.55 / 0.8) land on keys;
 * a Catmull-Rom spline through the keys keeps position and aim smooth across them.
 */
export const CAMERA_KEYS: CameraKey[] = [
  { p: 0, pos: new Vector3(-8, 6, 64), look: new Vector3(0, 0, 0) },
  { p: 0.15, pos: new Vector3(5, 5, 31), look: new Vector3(-3, 1, 0) },
  { p: 0.35, pos: new Vector3(15, 11, 19), look: new Vector3(0, 4, 4) },
  { p: 0.55, pos: patchPoint(0, 5.2, 3.6), look: patchPoint(0, 0, 0) },
  { p: 0.8, pos: patchPoint(0.3, 3.4, 4.8), look: hot(0.7) },
  { p: 1, pos: patchPoint(0, 8.5, 1.5), look: patchPoint(0, 0, 0) },
];

function catmull(a: number, b: number, c: number, d: number, t: number) {
  const t2 = t * t;
  const t3 = t2 * t;
  return 0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t3);
}

function spline(pick: (k: CameraKey) => Vector3, i: number, t: number, out: Vector3) {
  const k0 = pick(CAMERA_KEYS[Math.max(i - 1, 0)]);
  const k1 = pick(CAMERA_KEYS[i]);
  const k2 = pick(CAMERA_KEYS[i + 1]);
  const k3 = pick(CAMERA_KEYS[Math.min(i + 2, CAMERA_KEYS.length - 1)]);
  out.set(
    catmull(k0.x, k1.x, k2.x, k3.x, t),
    catmull(k0.y, k1.y, k2.y, k3.y, t),
    catmull(k0.z, k1.z, k2.z, k3.z, t),
  );
}

export function sampleCamera(progress: number, pos: Vector3, look: Vector3) {
  const p = clamp01(progress);
  let i = 0;
  while (i < CAMERA_KEYS.length - 2 && p > CAMERA_KEYS[i + 1].p) i++;
  const t = (p - CAMERA_KEYS[i].p) / (CAMERA_KEYS[i + 1].p - CAMERA_KEYS[i].p);
  spline((k) => k.pos, i, t, pos);
  spline((k) => k.look, i, t, look);
}
