"use client";

import { Menu, Satellite, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { scrollToSection } from "./scroller";
import { SECTIONS, activeSection, hashToSectionId, type SectionId } from "./sections";

/** Fixed header: anchors (through Lenis), active-section tracking, hash sync, page progress, mobile menu. */
export function SiteNav() {
  const [active, setActive] = useState<SectionId>("home");
  const [open, setOpen] = useState(false);
  const bar = useRef<HTMLDivElement>(null);
  const header = useRef<HTMLElement>(null);
  const ready = useRef(false);

  const go = useCallback((id: SectionId) => {
    setOpen(false);
    history.pushState(null, "", id === "home" ? location.pathname + location.search : `#${id}`);
    scrollToSection(id);
  }, []);

  useEffect(() => {
    history.scrollRestoration = "manual";
    let raf = 0;
    let hashTimer: ReturnType<typeof setTimeout> | undefined;

    const update = () => {
      raf = 0;
      const tops: Partial<Record<SectionId, number>> = {};
      for (const s of SECTIONS) {
        const el = document.getElementById(s.id);
        if (el) tops[s.id] = el.getBoundingClientRect().top;
      }
      const max = document.documentElement.scrollHeight - innerHeight;
      const atBottom = max > 0 && scrollY >= max - 4;
      const id = activeSection(tops, innerHeight, atBottom);
      setActive(id);
      if (bar.current) bar.current.style.transform = `scaleX(${max > 0 ? Math.min(1, scrollY / max) : 0})`;
      header.current?.setAttribute("data-scrolled", scrollY > 40 ? "true" : "false");
      // Keep the URL hash in step with the section, debounced so a smooth-scroll doesn't spam history.
      clearTimeout(hashTimer);
      hashTimer = setTimeout(() => {
        if (!ready.current) return;
        const want = id === "home" ? "" : `#${id}`;
        if (location.hash !== want) history.replaceState(null, "", location.pathname + location.search + want);
      }, 200);
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(update);
    };
    const onPop = () => scrollToSection(hashToSectionId(location.hash));

    // Landing on /#contact: the hero pin changes page height as it lays out, so keep re-applying
    // the jump (for up to ~10s) until the target sits at the top or the user takes over.
    const target = hashToSectionId(location.hash);
    let userMoved = false;
    const stop = () => (userMoved = true);
    for (const ev of ["wheel", "touchstart", "keydown"]) addEventListener(ev, stop, { once: true, passive: true });
    let tries = 0;
    const settle = setInterval(() => {
      const el = document.getElementById(target);
      const off = el ? Math.abs(el.getBoundingClientRect().top) : 0;
      if (location.hash && target !== "home" && !userMoved && off > 8 && tries < 40) {
        scrollToSection(target, { immediate: true });
        tries++;
        return;
      }
      clearInterval(settle);
      ready.current = true;
      update();
    }, 250);

    addEventListener("scroll", onScroll, { passive: true });
    addEventListener("resize", onScroll);
    addEventListener("popstate", onPop);
    update();
    return () => {
      removeEventListener("scroll", onScroll);
      removeEventListener("resize", onScroll);
      removeEventListener("popstate", onPop);
      cancelAnimationFrame(raf);
      clearTimeout(hashTimer);
      clearInterval(settle);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [open]);

  const link = (id: SectionId, label: string, mobile = false) => (
    <a
      key={id}
      href={id === "home" ? "#home" : `#${id}`}
      aria-current={active === id ? "location" : undefined}
      onClick={(e) => {
        e.preventDefault();
        go(id);
      }}
      className={cn(
        "font-mono text-[11px] uppercase tracking-[0.25em] transition-colors hover:text-accent",
        mobile ? "block py-3 text-sm" : "py-2",
        active === id ? "text-accent" : "text-ink-muted",
      )}
    >
      {label}
    </a>
  );

  return (
    <header
      ref={header}
      data-scrolled="false"
      className="group fixed inset-x-0 top-0 z-50 border-b border-transparent transition-colors data-[scrolled=true]:border-line data-[scrolled=true]:bg-canvas/90"
    >
      <a
        href="#main"
        className="absolute left-4 top-2 -translate-y-16 bg-canvas px-3 py-2 font-mono text-xs text-accent focus:translate-y-0"
      >
        Skip to content
      </a>
      <div className="flex items-center justify-between px-6 py-3 md:px-16">
        <a
          href="#home"
          onClick={(e) => {
            e.preventDefault();
            go("home");
          }}
          className="flex items-center gap-2.5 text-xs font-semibold tracking-[0.25em]"
        >
          <Satellite aria-hidden className="h-4 w-4 text-accent" />
          PRECURSOR AI
        </a>
        <nav aria-label="Primary" className="hidden items-center gap-8 md:flex">
          {SECTIONS.map((s) => link(s.id, s.label))}
          <Link
            href="/dashboard"
            className="border border-accent/60 bg-accent/10 px-4 py-2 font-mono text-[11px] uppercase tracking-[0.25em] text-accent transition-colors hover:bg-accent hover:text-canvas"
          >
            Dashboard
          </Link>
        </nav>
        <button
          type="button"
          aria-expanded={open}
          aria-controls="mobile-menu"
          aria-label={open ? "Close menu" : "Open menu"}
          onClick={() => setOpen((v) => !v)}
          className="-mr-2 p-2 text-ink md:hidden"
        >
          {open ? <X aria-hidden className="h-5 w-5" /> : <Menu aria-hidden className="h-5 w-5" />}
        </button>
      </div>
      {open && (
        <nav id="mobile-menu" aria-label="Primary mobile" className="border-t border-line bg-canvas px-6 pb-4 md:hidden">
          {SECTIONS.map((s) => link(s.id, s.label, true))}
          <Link href="/dashboard" className="block py-3 font-mono text-sm uppercase tracking-[0.25em] text-accent">
            Dashboard
          </Link>
        </nav>
      )}
      <div aria-hidden className="absolute inset-x-0 bottom-0 h-[2px] bg-line/60">
        <div ref={bar} className="h-full origin-left bg-accent" style={{ transform: "scaleX(0)" }} />
      </div>
    </header>
  );
}
