"use client";

import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useEffect } from "react";
import { prefersReducedMotion } from "./scroller";

/**
 * The page's one section-transition language: elements marked `data-reveal` fade up
 * (opacity + translateY, staggered) as they enter, and `data-rule` hairlines draw across (scaleX).
 * Content is server-rendered visible; this only hides-then-reveals it once JS runs.
 * Reduced motion: does nothing, so everything stays visible.
 */
export function Reveal() {
  useEffect(() => {
    if (prefersReducedMotion()) return;
    gsap.registerPlugin(ScrollTrigger);
    const ctx = gsap.context(() => {
      const items = gsap.utils.toArray<HTMLElement>("[data-reveal]");
      gsap.set(items, { autoAlpha: 0, y: 24 });
      ScrollTrigger.batch(items, {
        start: "top 90%",
        once: true,
        onEnter: (batch) => gsap.to(batch, { autoAlpha: 1, y: 0, duration: 0.8, ease: "power2.out", stagger: 0.07, overwrite: true }),
      });
      for (const rule of gsap.utils.toArray<HTMLElement>("[data-rule]")) {
        gsap.set(rule, { scaleX: 0, transformOrigin: "0 50%" });
        ScrollTrigger.create({
          trigger: rule,
          start: "top 92%",
          once: true,
          onEnter: () => gsap.to(rule, { scaleX: 1, duration: 1.1, ease: "power2.out" }),
        });
      }
    });
    return () => ctx.revert();
  }, []);
  return null;
}
