import { Vector3 } from "three";
import { SUN_DIR } from "../utils/geo";
import { HOT, HOT2, TERRAIN_SIZE } from "../utils/terrain";
import { NOISE_GLSL } from "./noise";

const f = (n: number) => n.toFixed(4);

// Synthetic deformation field: two Gaussian bowls. Illustrative only, not a measurement.
const MATH = /* glsl */ `
#define TERR_HALF ${f(TERRAIN_SIZE / 2)}
float gauss2(vec2 p, vec2 c, float s){ vec2 d = (p - c) / s; return exp(-dot(d, d)); }
float hotA(vec2 p){ return gauss2(p, vec2(${f(HOT.x)}, ${f(HOT.z)}), ${f(HOT.sigma)}); }
float hotB(vec2 p){ return 0.55 * gauss2(p, vec2(${f(HOT2.x)}, ${f(HOT2.z)}), ${f(HOT2.sigma)}); }
float deformField(vec2 p){ return -(hotA(p) + hotB(p)); }
`;

const VARYINGS = /* glsl */ `
varying vec2 vXZ;
varying float vH;
varying float vDef;
varying float vSlope;
varying vec3 vWorldN;
`;

/** Shared by terrain and heatmap so both displace identically. */
export const TERRAIN_VERT = /* glsl */ `
uniform float uRelief;
uniform float uFlat;
uniform float uDeform;
${MATH}
${VARYINGS}
void main(){
  vec3 p = position;
  float hFull = p.y * uRelief;
  float h = hFull * mix(1.0, 0.12, uFlat);
  float d = deformField(p.xz);
  vXZ = p.xz;
  vH = hFull; // colour/contours use the unflattened height
  vDef = d;
  vSlope = 1.0 - normal.y;
  vWorldN = normalize(mat3(modelMatrix) * normal);
  p.y = 0.3 + h + d * uDeform; // hovers above the globe so subsidence never digs through it
  gl_Position = projectionMatrix * viewMatrix * modelMatrix * vec4(p, 1.0);
}`;

const HELPERS = /* glsl */ `
float gridLines(vec2 p, float s){
  vec2 q = p / s;
  vec2 g = abs(fract(q - 0.5) - 0.5) / max(fwidth(q), vec2(1e-4));
  return 1.0 - min(min(g.x, g.y), 1.0);
}
float isoLines(float k){
  float w = max(fwidth(k), 1e-4);
  return 1.0 - smoothstep(0.0, 1.5 * w, abs(fract(k - 0.5) - 0.5));
}
`;

export const TERRAIN_FRAG = /* glsl */ `
uniform float uTime;
uniform float uAppear;
uniform float uSar;
uniform float uInsar;
uniform float uTopo;
uniform float uFlat;
uniform float uScan;
uniform vec3 uSun;
${NOISE_GLSL}
${MATH}
${VARYINGS}
${HELPERS}
void main(){
  float r = length(vXZ) / TERR_HALF;
  float edge = 1.0 - smoothstep(0.78, 1.0, r);
  float shade = clamp(dot(normalize(vWorldN), uSun) * 0.5 + 0.5, 0.0, 1.0);

  // 1) SAR amplitude look: speckle x terrain brightness (radar-green tint).
  float speckle = hash31(vec3(floor(vXZ * 80.0), 3.0));
  float tex = 0.6 + 0.8 * fbm3(vec3(vXZ * 1.8, 1.0));
  float amp = (0.25 + 0.6 * shade) * (0.45 + 0.9 * speckle) * tex;
  vec3 sarCol = vec3(0.40, 0.85, 0.72) * amp * 0.75;

  // 2) Interferogram look: wrapped phase fringes where coherence is high.
  float atmos = fbm3(vec3(vXZ * 0.8, 9.0));
  float phase = -vDef * 3.0 + 0.35 * atmos;
  vec3 fringe = 0.5 + 0.5 * cos(6.28318 * (fract(phase) + vec3(0.0, 0.33, 0.67)));
  float coh = smoothstep(0.30, 0.60, fbm3(vec3(vXZ * 2.4, 5.0)) + 0.3 * (1.0 - smoothstep(0.0, 0.25, vSlope)));
  vec3 insarCol = mix(vec3(amp * 0.5), fringe * (0.55 + 0.45 * shade), coh);
  vec3 col = mix(sarCol, insarCol, uInsar);

  // 3) Terrain model: hypsometric tint + cyan elevation / orange deformation contours.
  vec3 hyps = mix(vec3(0.03, 0.10, 0.16), vec3(0.20, 0.34, 0.30), smoothstep(0.0, 0.5, vH));
  hyps = mix(hyps, vec3(0.62, 0.56, 0.46), smoothstep(0.55, 1.0, vH));
  col = mix(col, hyps * (0.30 + 0.95 * shade), uTopo);
  col = mix(col, vec3(0.20, 0.80, 1.0), isoLines(vH / 0.1) * 0.5 * uTopo);
  col = mix(col, vec3(1.0, 0.55, 0.12), isoLines(vDef * 6.0) * step(0.001, -vDef) * 0.8 * uTopo);

  col += vec3(0.10, 0.65, 0.90) * gridLines(vXZ, 0.25) * 0.22 * uSar;
  col += vec3(0.3, 1.0, 0.7) * exp(-abs(vXZ.x - uScan) * 10.0) * 0.45 * uSar * (1.0 - uTopo);

  float luma = dot(col, vec3(0.333));
  col = mix(col, vec3(luma) * vec3(0.55, 0.85, 1.1), uFlat * 0.45) * mix(1.0, 0.7, uFlat);
  gl_FragColor = vec4(col, uAppear * edge);
  #include <colorspace_fragment>
}`;

export const HEAT_FRAG = /* glsl */ `
uniform float uTime;
uniform float uRisk;
uniform float uFlat;
${NOISE_GLSL}
${MATH}
${VARYINGS}
${HELPERS}
void main(){
  float r = length(vXZ) / TERR_HALF;
  float edge = 1.0 - smoothstep(0.78, 1.0, r);
  // Illustrative relative score from synthetic hotspots + slope. Not a calibrated probability.
  float risk = 0.8 * hotA(vXZ) + 0.9 * hotB(vXZ) + 0.3 * smoothstep(0.03, 0.2, vSlope)
             + 0.12 * fbm3(vec3(vXZ * 2.0, 4.0)) - 0.1;
  risk = clamp(risk, 0.0, 1.0);
  risk += 0.03 * sin(uTime * 2.0 + risk * 10.0);
  risk = mix(risk, floor(risk * 4.0) / 4.0 + 0.125, uFlat); // class map in the final scene
  vec3 c = mix(vec3(1.0, 0.72, 0.12), vec3(1.0, 0.38, 0.05), smoothstep(0.35, 0.65, risk));
  c = mix(c, vec3(0.95, 0.12, 0.10), smoothstep(0.65, 0.95, risk));
  c += isoLines(risk * 8.0) * 0.25;
  float a = uRisk * smoothstep(0.38, 0.7, risk) * (0.30 + 0.55 * risk) * edge * (1.0 + 0.3 * uFlat);
  gl_FragColor = vec4(c, a);
  #include <colorspace_fragment>
}`;

export interface TerrainUniforms {
  [k: string]: { value: number | Vector3 };
  uTime: { value: number };
  uAppear: { value: number };
  uSar: { value: number };
  uInsar: { value: number };
  uTopo: { value: number };
  uRisk: { value: number };
  uFlat: { value: number };
  uScan: { value: number };
  uRelief: { value: number };
  uDeform: { value: number };
  uSun: { value: Vector3 };
}

export function createTerrainUniforms(): TerrainUniforms {
  return {
    uTime: { value: 0 },
    uAppear: { value: 0 },
    uSar: { value: 0 },
    uInsar: { value: 0 },
    uTopo: { value: 0 },
    uRisk: { value: 0 },
    uFlat: { value: 0 },
    uScan: { value: 0 },
    uRelief: { value: 0 },
    uDeform: { value: 0 },
    uSun: { value: SUN_DIR },
  };
}
