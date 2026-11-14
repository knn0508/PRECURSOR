"use client";

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { Group, Vector3 } from "three";
import { progress } from "../animations/progress";
import { ParticleField } from "../effects/ParticleField";
import { RadarBeam } from "../effects/RadarBeam";
import { RadarWaves } from "../effects/RadarWaves";
import { SatelliteOrbit } from "../effects/SatelliteOrbit";
import { SatelliteModel } from "../objects/SatelliteModel";
import { EARTH_R, ORBIT_R, orbitPoint } from "../utils/geo";
import { smooth } from "../utils/math";

export interface SatState {
  pos: Vector3;
  /** Ground footprint (side-looking: slightly ahead of nadir along the orbit). */
  target: Vector3;
  /** 0..1 visibility of the satellite and its radar effects. */
  vis: number;
}

export function SatelliteScene({ mobile }: { mobile: boolean }) {
  const group = useRef<Group>(null);
  const state = useMemo<SatState>(() => ({ pos: new Vector3(), target: new Vector3(), vis: 0 }), []);

  useFrame(() => {
    const p = progress.p;
    // theta = 0 (directly over the monitored patch) at p = 0.38; satellite enters from the limb at p ~ 0.12.
    const theta = (p - 0.38) * 9.2;
    orbitPoint(theta, ORBIT_R, state.pos);
    orbitPoint(theta + 0.14, EARTH_R, state.target);
    state.vis = smooth(0.1, 0.16, p) * (1 - smooth(0.4, 0.46, p));
    const g = group.current;
    if (!g) return;
    g.visible = state.vis > 0.01;
    g.position.copy(state.pos);
    g.lookAt(0, 0, 0); // local +z (antenna side) faces Earth
    g.scale.setScalar(1.5 * state.vis);
  });

  return (
    <>
      <SatelliteOrbit />
      <SatelliteModel ref={group} />
      <RadarBeam state={state} />
      <RadarWaves state={state} />
      <ParticleField state={state} count={mobile ? 120 : 300} />
    </>
  );
}
