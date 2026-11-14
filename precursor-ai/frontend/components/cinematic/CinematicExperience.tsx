"use client";

import dynamic from "next/dynamic";
import { Component, useRef, type ReactNode } from "react";
import { Chrome } from "./overlays/Chrome";
import { ChapterOverlay } from "./overlays/ChapterOverlay";
import { Hud } from "./overlays/Hud";
import { StaticFallback } from "./overlays/StaticFallback";
import { useCinematicEnv } from "./hooks/useCinematicEnv";
import { useScrollTimeline } from "./hooks/useScrollTimeline";

// Three.js is only fetched when the cinematic actually renders.
const CinematicCanvas = dynamic(() => import("./scenes/CinematicCanvas"), { ssr: false });

class Boundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: unknown) {
    console.error("Cinematic experience failed, showing static fallback", error);
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

function Stage({ mobile }: { mobile: boolean }) {
  const root = useRef<HTMLDivElement>(null);
  useScrollTimeline(root, mobile);
  return (
    <div ref={root} className="relative h-screen w-full overflow-hidden bg-[#02040a]">
      <div className="absolute inset-0">
        <CinematicCanvas mobile={mobile} />
      </div>
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 z-[5]"
        style={{ background:
            "linear-gradient(to top, rgba(2,4,10,0.7), transparent 45%), radial-gradient(ellipse at center, transparent 55%, rgba(2,4,10,0.6) 100%)" }}
      />
      <ChapterOverlay />
      <Hud />
      <Chrome />
    </div>
  );
}

export function CinematicExperience() {
  const env = useCinematicEnv();
  if (!env) return <div className="h-screen bg-[#02040a]" />;
  if (!env.webgl) return <StaticFallback reason="WebGL unavailable" />;
  if (env.reducedMotion) return <StaticFallback reason="Reduced motion" />;
  return (
    <Boundary fallback={<StaticFallback reason="3D unavailable" />}>
      <Stage mobile={env.mobile} />
    </Boundary>
  );
}
