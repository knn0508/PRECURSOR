import { PlaneGeometry } from "three";

/**
 * Procedural, synthetic terrain. It is NOT a real DEM; it only gives the
 * visualization plausible relief. Deformation hotspots are also synthetic.
 */
export const TERRAIN_SIZE = 5;
export const HOT = { x: 0.55, z: -0.25, sigma: 0.75 };
export const HOT2 = { x: -1.0, z: 0.9, sigma: 0.45 };

function hash2(ix: number, iy: number) {
  let h = Math.imul(ix, 374761393) + Math.imul(iy, 668265263);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
}

function vnoise(x: number, y: number) {
  const ix = Math.floor(x);
  const iy = Math.floor(y);
  const fx = x - ix;
  const fy = y - iy;
  const u = fx * fx * (3 - 2 * fx);
  const v = fy * fy * (3 - 2 * fy);
  const a = hash2(ix, iy);
  const b = hash2(ix + 1, iy);
  const c = hash2(ix, iy + 1);
  const d = hash2(ix + 1, iy + 1);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
}

function fbm(x: number, y: number) {
  let sum = 0;
  let amp = 0.5;
  for (let i = 0; i < 5; i++) {
    sum += amp * vnoise(x, y);
    x = x * 2.03 + 17.1;
    y = y * 2.03 + 9.7;
    amp *= 0.5;
  }
  return sum;
}

/** Height (world units, local up) at plane coordinates x, z. Zero at the patch rim. */
export function terrainHeight(x: number, z: number) {
  const r = Math.hypot(x, z) / (TERRAIN_SIZE / 2);
  const t = Math.min(1, Math.max(0, (r - 0.7) / 0.3));
  const falloff = 1 - t * t * (3 - 2 * t);
  const base = Math.max(0, 1.5 * (fbm(x * 0.7 + 10, z * 0.7 + 10) - 0.35));
  const ridge = 1 - Math.abs(2 * fbm(x * 0.45 + 3, z * 0.45 + 41) - 1);
  return (base + 0.35 * ridge * ridge) * falloff;
}

/** Plane in XZ (normal +y) with baked heights. Shared by terrain and heatmap meshes. */
export function buildTerrainGeometry(segments: number) {
  const geo = new PlaneGeometry(TERRAIN_SIZE, TERRAIN_SIZE, segments, segments);
  geo.rotateX(-Math.PI / 2);
  const pos = geo.attributes.position;
  for (let i = 0; i < pos.count; i++) pos.setY(i, terrainHeight(pos.getX(i), pos.getZ(i)));
  geo.computeVertexNormals();
  return geo;
}
