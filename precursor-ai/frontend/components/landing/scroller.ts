import type Lenis from "lenis";
import { type SectionId } from "./sections";

/**
 * The cinematic hero owns the one Lenis instance and registers it here, so nav anchors
 * scroll through the same smoother. With no Lenis (reduced motion / no WebGL) jumps are native and instant.
 */
let lenis: Lenis | null = null;

export function setLenis(instance: Lenis | null) {
  lenis = instance;
}

export function prefersReducedMotion() {
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function scrollToSection(id: SectionId, opts: { immediate?: boolean } = {}) {
  const el = id === "home" ? null : document.getElementById(id);
  const instant = opts.immediate || prefersReducedMotion();
  if (lenis && !prefersReducedMotion()) {
    lenis.scrollTo(el ?? 0, { immediate: opts.immediate, duration: 1.6 });
  } else if (el) {
    el.scrollIntoView({ behavior: instant ? "instant" : "auto", block: "start" });
  } else {
    window.scrollTo({ top: 0, behavior: "instant" });
  }
}
