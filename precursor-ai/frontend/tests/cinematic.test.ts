import { describe, expect, it } from "vitest";
import { Vector3 } from "three";
import { CAMERA_KEYS, sampleCamera } from "@/components/cinematic/animations/cameraPath";
import { CHAPTERS } from "@/components/cinematic/animations/chapters";
import { EARTH_R, ORBIT_R, PATCH_CENTER, PATCH_NORMAL, PATCH_QUAT, orbitPoint } from "@/components/cinematic/utils/geo";
import { range, smooth } from "@/components/cinematic/utils/math";
import { TERRAIN_SIZE, buildTerrainGeometry, terrainHeight } from "@/components/cinematic/utils/terrain";

describe("math", () => {
  it("ramps are clamped and monotonic", () => {
    expect(range(0.2, 0.4, 0)).toBe(0);
    expect(range(0.2, 0.4, 1)).toBe(1);
    expect(smooth(0.2, 0.4, 0.3)).toBeCloseTo(0.5);
    expect(smooth(0.2, 0.4, 0.35)).toBeGreaterThan(smooth(0.2, 0.4, 0.25));
  });
});

describe("chapters", () => {
  it("are contiguous and cover the whole journey", () => {
    expect(CHAPTERS).toHaveLength(5);
    expect(CHAPTERS[0].range[0]).toBe(0);
    expect(CHAPTERS.at(-1)!.range[1]).toBe(1);
    for (let i = 1; i < CHAPTERS.length; i++) expect(CHAPTERS[i].range[0]).toBe(CHAPTERS[i - 1].range[1]);
  });
});

describe("camera path", () => {
  it("passes exactly through each keyframe", () => {
    const pos = new Vector3();
    const look = new Vector3();
    for (const k of CAMERA_KEYS) {
      sampleCamera(k.p, pos, look);
      expect(pos.distanceTo(k.pos)).toBeLessThan(1e-6);
      expect(look.distanceTo(k.look)).toBeLessThan(1e-6);
    }
  });

  it("is continuous: no jump between neighbouring scroll samples", () => {
    const a = new Vector3();
    const b = new Vector3();
    const la = new Vector3();
    const lb = new Vector3();
    for (let p = 0; p < 1; p += 0.002) {
      sampleCamera(p, a, la);
      sampleCamera(p + 0.002, b, lb);
      expect(a.distanceTo(b)).toBeLessThan(1.2);
      expect(la.distanceTo(lb)).toBeLessThan(0.6);
    }
  });

  it("clamps outside 0..1 and never produces NaN", () => {
    const pos = new Vector3();
    const look = new Vector3();
    for (const p of [-1, 0, 0.5, 1, 2]) {
      sampleCamera(p, pos, look);
      expect([pos.x, pos.y, pos.z, look.x, look.y, look.z].every(Number.isFinite)).toBe(true);
    }
  });

  it("never enters the globe", () => {
    const pos = new Vector3();
    const look = new Vector3();
    for (let p = 0; p <= 1; p += 0.005) {
      sampleCamera(p, pos, look);
      expect(pos.length()).toBeGreaterThan(EARTH_R + 1);
    }
  });
});

describe("patch frame and orbit", () => {
  it("maps local up to the surface normal and sits on the globe", () => {
    const up = new Vector3(0, 1, 0).applyQuaternion(PATCH_QUAT);
    expect(up.distanceTo(PATCH_NORMAL)).toBeLessThan(1e-6);
    expect(PATCH_CENTER.length()).toBeCloseTo(EARTH_R);
  });

  it("orbit passes directly over the patch at theta = 0", () => {
    const p = orbitPoint(0);
    expect(p.distanceTo(PATCH_NORMAL.clone().multiplyScalar(ORBIT_R))).toBeLessThan(1e-9);
    expect(orbitPoint(1.234).length()).toBeCloseTo(ORBIT_R);
  });
});

describe("terrain", () => {
  it("is deterministic, finite, non-negative and zero at the rim", () => {
    expect(terrainHeight(0.3, -0.7)).toBe(terrainHeight(0.3, -0.7));
    for (let x = -2.5; x <= 2.5; x += 0.25) {
      for (let z = -2.5; z <= 2.5; z += 0.25) {
        const h = terrainHeight(x, z);
        expect(Number.isFinite(h)).toBe(true);
        expect(h).toBeGreaterThanOrEqual(0);
      }
    }
    expect(terrainHeight(TERRAIN_SIZE / 2, 0)).toBe(0);
  });

  it("builds a grid with the expected vertex count and upward normals", () => {
    const g = buildTerrainGeometry(16);
    expect(g.attributes.position.count).toBe(17 * 17);
    let up = 0;
    for (let i = 0; i < g.attributes.normal.count; i++) if (g.attributes.normal.getY(i) > 0) up++;
    expect(up).toBe(g.attributes.normal.count);
    g.dispose();
  });
});
