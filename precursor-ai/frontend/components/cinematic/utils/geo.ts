import { Matrix4, Quaternion, Vector3 } from "three";

/** World units. The satellite and the terrain patch are exaggerated for legibility. */
export const EARTH_R = 10;
export const ORBIT_R = 14.5;

const LAT = (38 * Math.PI) / 180;

/** Direction of the monitored terrain patch on the globe (Earth-local, equals world once Earth stops spinning). */
export const PATCH_NORMAL = new Vector3(0, Math.sin(LAT), Math.cos(LAT));
export const PATCH_EAST = new Vector3(1, 0, 0);
/** east x normal = south, so the local frame (x east, y up, z south) is right-handed. */
export const PATCH_SOUTH = new Vector3().crossVectors(PATCH_EAST, PATCH_NORMAL);
export const PATCH_CENTER = PATCH_NORMAL.clone().multiplyScalar(EARTH_R);
export const PATCH_QUAT = new Quaternion().setFromRotationMatrix(
  new Matrix4().makeBasis(PATCH_EAST, PATCH_NORMAL, PATCH_SOUTH),
);

/** World-space point at local patch coordinates (east, up, south). */
export function patchPoint(east: number, up: number, south: number, out = new Vector3()) {
  return out
    .copy(PATCH_CENTER)
    .addScaledVector(PATCH_EAST, east)
    .addScaledVector(PATCH_NORMAL, up)
    .addScaledVector(PATCH_SOUTH, south);
}

/** Orbit lies in the plane spanned by the patch normal and east, so theta = 0 is directly above the patch. */
export function orbitPoint(theta: number, radius = ORBIT_R, out = new Vector3()) {
  return out
    .copy(PATCH_NORMAL)
    .multiplyScalar(Math.cos(theta) * radius)
    .addScaledVector(PATCH_EAST, Math.sin(theta) * radius);
}

export const SUN_DIR = new Vector3(60, 24, 80).normalize();
