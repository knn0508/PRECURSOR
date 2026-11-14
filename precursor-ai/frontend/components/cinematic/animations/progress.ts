/**
 * Single source of truth for the journey: scroll progress 0..1.
 * Written ONLY by the master GSAP timeline; read every frame by the 3D scene
 * (no React state, so scrolling never re-renders anything).
 */
export const progress = { p: 0 };
