export const clamp01 = (x: number) => Math.min(1, Math.max(0, x));

/** Linear 0..1 ramp of x between a and b. */
export const range = (a: number, b: number, x: number) => clamp01((x - a) / (b - a));

/** Smoothstep ramp of x between a and b. */
export const smooth = (a: number, b: number, x: number) => {
  const t = range(a, b, x);
  return t * t * (3 - 2 * t);
};
