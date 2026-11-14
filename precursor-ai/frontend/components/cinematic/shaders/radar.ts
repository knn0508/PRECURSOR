/** Artistic radar effects. These are illustrations, not NISAR/Sentinel-1 measurements. */

export const BEAM_VERT = /* glsl */ `
varying float vZ;
void main(){
  vZ = position.z; // 0 at the antenna, 1 at the ground footprint
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

export const BEAM_FRAG = /* glsl */ `
uniform float uTime;
uniform float uIntensity;
varying float vZ;
void main(){
  float stripe = pow(0.5 + 0.5 * sin((vZ * 8.0 - uTime * 3.0) * 6.28318), 6.0);
  float a = (0.10 + 0.55 * stripe) * (1.0 - 0.3 * vZ) * uIntensity;
  gl_FragColor = vec4(mix(vec3(0.15, 0.85, 1.0), vec3(0.3, 1.0, 0.55), vZ), a);
  #include <colorspace_fragment>
}`;

export const WAVES_VERT = /* glsl */ `
varying vec2 vUv;
void main(){
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

export const WAVES_FRAG = /* glsl */ `
uniform float uTime;
uniform float uIntensity;
varying vec2 vUv;
void main(){
  float r = length(vUv * 2.0 - 1.0);
  float a = 0.0;
  for (int i = 0; i < 3; i++){
    float ph = fract(uTime * 0.35 + float(i) / 3.0);
    a += smoothstep(0.05, 0.0, abs(r - ph)) * (1.0 - ph);
  }
  a *= step(r, 1.0) * uIntensity;
  gl_FragColor = vec4(0.3, 1.0, 0.65, a);
  #include <colorspace_fragment>
}`;

export const PARTICLE_VERT = /* glsl */ `
uniform float uTime;
uniform float uSpeed;
uniform float uSize;
uniform vec3 uFrom;
uniform vec3 uTo;
attribute float aSeed;
attribute vec3 aJitter;
varying float vA;
void main(){
  float t = fract(uTime * uSpeed + aSeed);
  vec3 p = mix(uFrom, uTo, t) + aJitter * sin(t * 3.14159) * 0.35;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  vA = sin(t * 3.14159);
  gl_PointSize = uSize * (60.0 / -mv.z);
  gl_Position = projectionMatrix * mv;
}`;

export const PARTICLE_FRAG = /* glsl */ `
uniform float uIntensity;
varying float vA;
void main(){
  float d = length(gl_PointCoord - 0.5);
  float a = smoothstep(0.5, 0.0, d) * vA * uIntensity;
  gl_FragColor = vec4(0.4, 0.9, 1.0, a);
  #include <colorspace_fragment>
}`;
