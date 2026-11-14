"use client";

import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import Lenis from "lenis";
import { useEffect, type RefObject } from "react";
import { CHAPTERS } from "../animations/chapters";
import { progress } from "../animations/progress";
import { setLenis } from "@/components/landing/scroller";

const FADE = 0.03;

/**
 * The ONE master timeline: a single pinned ScrollTrigger scrubs a 0..1 timeline that
 * (a) tweens `progress.p` (read by every 3D object and the camera) and
 * (b) fades the DOM text/HUD at fixed positions. Nothing else owns scroll.
 */
export function useScrollTimeline(root: RefObject<HTMLElement | null>, mobile: boolean) {
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    gsap.registerPlugin(ScrollTrigger);

    const lenis = new Lenis({ lerp: 0.1 });
    setLenis(lenis);
    lenis.on("scroll", ScrollTrigger.update);
    const tick = (time: number) => lenis.raf(time * 1000);
    gsap.ticker.add(tick);
    gsap.ticker.lagSmoothing(0);

    const ctx = gsap.context(() => {
      const q = (s: string) => el.querySelector<HTMLElement>(s);
      const tl = gsap.timeline({
        defaults: { ease: "none" },
        scrollTrigger: {
          trigger: el,
          start: "top top",
          end: `+=${mobile ? 450 : 700}%`,
          pin: true,
          scrub: 1,
          anticipatePin: 1,
          refreshPriority: 1, // lay out the pin before the content-section reveal triggers below it
        },
      });

      tl.to(progress, { p: 1, duration: 1 }, 0);
      tl.to(q("[data-scroll-hint]"), { autoAlpha: 0, duration: 0.04 }, 0);

      CHAPTERS.forEach((c, i) => {
        const node = q(`[data-chapter="${c.id}"]`);
        if (!node) return;
        const [a, b] = c.range;
        if (i > 0) tl.fromTo(node, { autoAlpha: 0, y: 24 }, { autoAlpha: 1, y: 0, duration: FADE, ease: "power2.out" }, a + 0.01);
        if (i < CHAPTERS.length - 1) tl.to(node, { autoAlpha: 0, y: -24, duration: FADE, ease: "power2.in" }, b - FADE - 0.005);
      });

      tl.fromTo(q('[data-hud="legend"]'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.04 }, 0.67);
      tl.to(q('[data-hud="legend"]'), { autoAlpha: 0, duration: 0.04 }, 0.82);
      tl.fromTo(q('[data-hud="map"]'), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.06 }, 0.88);
    }, el);

    return () => {
      ctx.revert(); // kills the timeline and its ScrollTrigger (also unpins)
      gsap.ticker.remove(tick);
      setLenis(null);
      lenis.destroy();
      progress.p = 0;
    };
  }, [root, mobile]);
}
