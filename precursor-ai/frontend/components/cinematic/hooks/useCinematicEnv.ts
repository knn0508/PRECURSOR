"use client";

import { useEffect, useState } from "react";

export interface CinematicEnv {
  webgl: boolean;
  reducedMotion: boolean;
  mobile: boolean;
}

function hasWebGL() {
  try {
    const c = document.createElement("canvas");
    const gl = c.getContext("webgl2") ?? c.getContext("webgl");
    gl?.getExtension("WEBGL_lose_context")?.loseContext(); // free the probe context
    return !!gl;
  } catch {
    return false;
  }
}

/** null until mounted (capabilities are only known in the browser). */
export function useCinematicEnv(): CinematicEnv | null {
  const [env, setEnv] = useState<CinematicEnv | null>(null);
  useEffect(() => {
    setEnv({
      webgl: hasWebGL(),
      reducedMotion: matchMedia("(prefers-reduced-motion: reduce)").matches,
      mobile: matchMedia("(max-width: 767px), (pointer: coarse)").matches,
    });
  }, []);
  return env;
}
