import { NOISE_GLSL } from "./noise";

/** Earth: procedural fallback (fbm continents) that is replaced by the 59-earth textures once they load (uTex = 1). */
export const EARTH_VERT = /* glsl */ `
varying vec2 vUv;
varying vec3 vObj;
varying vec3 vN;
varying vec3 vWorld;
void main(){
  vUv = uv;
  vObj = position;
  vN = normalize(mat3(modelMatrix) * normal);
  vec4 w = modelMatrix * vec4(position, 1.0);
  vWorld = w.xyz;
  gl_Position = projectionMatrix * viewMatrix * w;
}`;

export const EARTH_FRAG = /* glsl */ `
uniform vec3 uSun;
uniform float uData;
uniform float uTex;
uniform sampler2D uAlbedo;
uniform sampler2D uMask;
uniform sampler2D uBump;
uniform sampler2D uNight;
${NOISE_GLSL}
varying vec2 vUv;
varying vec3 vObj;
varying vec3 vN;
varying vec3 vWorld;

float gridLines(vec2 p){
  vec2 g = abs(fract(p - 0.5) - 0.5) / max(fwidth(p), vec2(1e-4));
  return 1.0 - min(min(g.x, g.y), 1.0);
}

void main(){
  vec3 d = normalize(vObj);
  float h = fbm3(d * 2.4 + 3.0);
  float h2 = fbm3(d * 9.0);
  float land = smoothstep(0.50, 0.53, h);
  float lat = abs(d.y);

  vec3 ocean = mix(vec3(0.01, 0.05, 0.16), vec3(0.03, 0.20, 0.34), smoothstep(0.36, 0.50, h));
  float dry = smoothstep(0.2, 0.5, fbm3(d * 3.1 + 7.0));
  vec3 landc = mix(vec3(0.10, 0.22, 0.08), vec3(0.38, 0.31, 0.18), dry * (1.0 - lat));
  landc = mix(landc, vec3(0.56, 0.52, 0.45), smoothstep(0.58, 0.70, h) * 0.7);
  landc *= 0.75 + 0.5 * h2;
  vec3 col = mix(ocean, landc, land);
  col = mix(col, vec3(0.86, 0.90, 0.95), smoothstep(0.80, 0.90, lat + (h2 - 0.5) * 0.1));
  if (uTex > 0.5) {
    col = texture2D(uAlbedo, vUv).rgb;
    land = texture2D(uMask, vUv).r;
    h2 = 0.5 + (texture2D(uBump, vUv).r - 0.12) * 1.6;
  }

  vec3 N = normalize(vN);
  vec3 V = normalize(cameraPosition - vWorld);
  float bump = (h2 - 0.5) * land * 0.18;
  float ndl = dot(N, uSun) + bump;
  float day = smoothstep(-0.1, 0.25, ndl);
  vec3 lit = col * (0.04 + max(ndl, 0.0) * 1.05);
  vec3 H = normalize(uSun + V);
  lit += vec3(0.9, 0.95, 1.0) * pow(max(dot(N, H), 0.0), 220.0) * (1.0 - land) * 0.1 * day;
  lit += vec3(0.6, 0.25, 0.1) * smoothstep(0.0, 0.3, ndl) * (1.0 - smoothstep(0.3, 0.6, ndl)) * 0.08;
  lit += vec3(0.10, 0.35, 0.90) * pow(1.0 - max(dot(N, V), 0.0), 3.0) * 0.5 * day;
  if (uTex > 0.5) lit += vec3(1.0, 0.72, 0.38) * texture2D(uNight, vUv).r * 4.0 * (1.0 - day);

  // Radar-data mode: the globe becomes a dark graticule around the monitored patch.
  vec2 gp = vec2(atan(d.z, d.x) * 12.0 / 6.28318, asin(clamp(d.y, -1.0, 1.0)) * 12.0 / 3.14159);
  vec3 dataCol = vec3(0.008, 0.02, 0.04) + col * 0.05 + vec3(0.08, 0.45, 0.75) * gridLines(gp) * 0.35;
  gl_FragColor = vec4(mix(lit, dataCol, uData), 1.0);
  #include <colorspace_fragment>
}`;

export const CLOUD_FRAG = /* glsl */ `
uniform vec3 uSun;
uniform float uTime;
uniform float uFade;
uniform float uTex;
uniform sampler2D uClouds;
${NOISE_GLSL}
varying vec2 vUv;
varying vec3 vObj;
varying vec3 vN;
varying vec3 vWorld;
void main(){
  vec3 d = normalize(vObj);
  float c = fbm3(d * 4.5 + vec3(uTime * 0.01, 0.0, 0.0));
  float a = smoothstep(0.52, 0.74, c);
  if (uTex > 0.5) a = smoothstep(0.12, 0.85, texture2D(uClouds, vUv).r);
  float ndl = clamp(dot(normalize(vN), uSun), 0.0, 1.0);
  gl_FragColor = vec4(vec3(0.95, 0.97, 1.0) * (0.05 + ndl), a * 0.7 * uFade);
  #include <colorspace_fragment>
}`;

export const ATMOS_VERT = /* glsl */ `
varying vec3 vN;
varying vec3 vWorld;
void main(){
  vN = normalize(mat3(modelMatrix) * normal);
  vec4 w = modelMatrix * vec4(position, 1.0);
  vWorld = w.xyz;
  gl_Position = projectionMatrix * viewMatrix * w;
}`;

export const ATMOS_FRAG = /* glsl */ `
uniform vec3 uSun;
uniform float uFade;
varying vec3 vN;
varying vec3 vWorld;
void main(){
  vec3 V = normalize(cameraPosition - vWorld);
  float a = abs(dot(normalize(vN), V));
  float glow = pow(smoothstep(0.0, 0.5, a), 2.0);
  float sunSide = dot(normalize(vN), uSun) * 0.5 + 0.5;
  vec3 c = mix(vec3(0.05, 0.15, 0.45), vec3(0.25, 0.60, 1.0), sunSide);
  gl_FragColor = vec4(c * glow * 1.4, glow * uFade);
  #include <colorspace_fragment>
}`;
