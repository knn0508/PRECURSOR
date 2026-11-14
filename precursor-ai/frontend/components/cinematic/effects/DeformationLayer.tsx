"use client";

import { Html, Line } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import { BufferAttribute, BufferGeometry, DoubleSide, Group, MeshBasicMaterial, type Mesh } from "three";
import { progress } from "../animations/progress";
import { range, smooth } from "../utils/math";
import { HOT, terrainHeight } from "../utils/terrain";

/**
 * Illustrative 3D time-series above the synthetic hotspot, clearly split into
 * historical observations / current deformation / predicted movement / uncertainty envelope.
 * The curve is a hand-made shape with NO numeric axes: it is not a model output.
 */
const PW = 3; // plot width (world units) for s = 0..1
const PH = 0.8; // plot height
const S_NOW = 0.6;
const N = 48;
const disp = (s: number) => 0.25 * s + 0.6 * s ** 3;
const unc = (s: number) => 0.03 + 0.2 * Math.pow(Math.max(0, (s - S_NOW) / (1 - S_NOW)), 1.4);
const X_NOW = S_NOW * PW;

const sample = (a: number, b: number, shiftX: number) =>
  Array.from({ length: N + 1 }, (_, i) => {
    const s = a + ((b - a) * i) / N;
    return [s * PW - shiftX, disp(s) * PH, 0] as [number, number, number];
  });

function buildRibbon() {
  const pos: number[] = [];
  const idx: number[] = [];
  for (let i = 0; i <= N; i++) {
    const s = S_NOW + ((1 - S_NOW) * i) / N;
    const x = s * PW - X_NOW;
    const y = disp(s) * PH;
    pos.push(x, y + unc(s) * PH, 0, x, y - unc(s) * PH, 0);
    if (i < N) idx.push(2 * i, 2 * i + 1, 2 * i + 2, 2 * i + 1, 2 * i + 3, 2 * i + 2);
  }
  const g = new BufferGeometry();
  g.setAttribute("position", new BufferAttribute(new Float32Array(pos), 3));
  g.setIndex(idx);
  return g;
}

type LineLike = { material: { opacity: number } };

export function DeformationLayer() {
  const histG = useRef<Group>(null);
  const foreG = useRef<Group>(null);
  const markG = useRef<Group>(null);
  const ribbon = useRef<Mesh>(null);
  const histL = useRef<LineLike>(null);
  const foreL = useRef<LineLike>(null);
  const baseL = useRef<LineLike>(null);
  const labels = useRef<(HTMLDivElement | null)[]>([]);

  const data = useMemo(
    () => ({
      hist: sample(0, S_NOW, 0),
      fore: sample(S_NOW, 1, X_NOW),
      base: [
        [0, 0, 0],
        [PW, 0, 0],
      ] as [number, number, number][],
      drop: [
        [X_NOW, 0, 0],
        [X_NOW, disp(S_NOW) * PH, 0],
      ] as [number, number, number][],
      ribbonGeo: buildRibbon(),
      ribbonMat: new MeshBasicMaterial({ color: "#ff8a1f", transparent: true, opacity: 0, side: DoubleSide, depthWrite: false }),
    }),
    [],
  );
  useEffect(
    () => () => {
      data.ribbonGeo.dispose();
      data.ribbonMat.dispose();
    },
    [data],
  );

  useFrame(({ clock }) => {
    const p = progress.p;
    const out = 1 - smooth(0.82, 0.9, p);
    const hist = range(0.6, 0.67, p);
    const mark = smooth(0.66, 0.7, p);
    const fore = range(0.68, 0.75, p);
    const band = smooth(0.73, 0.78, p);

    if (histG.current) histG.current.scale.x = Math.max(hist, 0.001);
    if (foreG.current) foreG.current.scale.x = Math.max(fore, 0.001);
    if (markG.current) {
      markG.current.scale.setScalar(mark * (1 + 0.15 * Math.sin(clock.elapsedTime * 4)));
    }
    if (histL.current) histL.current.material.opacity = hist * out;
    if (foreL.current) foreL.current.material.opacity = fore * out;
    if (baseL.current) baseL.current.material.opacity = 0.3 * smooth(0.6, 0.66, p) * out;
    if (ribbon.current) ribbon.current.scale.x = Math.max(fore, 0.001);
    data.ribbonMat.opacity = 0.28 * band * out;

    const vis = [hist, mark, fore, band];
    labels.current.forEach((el, i) => {
      if (el) el.style.opacity = String(Math.max(0, vis[i] - 0.3) * 1.4 * out);
    });
  });

  const base = useMemo(
    () => [HOT.x - X_NOW, terrainHeight(HOT.x, HOT.z) + 1.0, HOT.z] as [number, number, number],
    [],
  );
  const setLabel = (i: number) => (el: HTMLDivElement | null) => {
    labels.current[i] = el;
  };
  const labelCls = "whitespace-nowrap font-mono text-[10px] uppercase tracking-[0.14em] opacity-0";

  return (
    <group position={base}>
      {/* @ts-expect-error drei Line ref is a Line2; only material.opacity is touched. */}
      <Line ref={baseL} points={data.base} color="#8b9bb0" lineWidth={1} transparent opacity={0} depthWrite={false} />
      <Line points={data.drop} color="#8b9bb0" lineWidth={1} transparent opacity={0.25} dashed dashSize={0.05} gapSize={0.05} />

      <group ref={histG}>
        {/* @ts-expect-error see above */}
        <Line ref={histL} points={data.hist} color="#38bdf8" lineWidth={2.5} transparent opacity={0} depthWrite={false} />
      </group>

      <group position={[X_NOW, 0, 0]}>
        <group ref={foreG}>
          {/* @ts-expect-error see above */}
          <Line ref={foreL} points={data.fore} color="#ff8a1f" lineWidth={2.5} dashed dashSize={0.1} gapSize={0.07} transparent opacity={0} depthWrite={false} />
          <mesh ref={ribbon} geometry={data.ribbonGeo} material={data.ribbonMat} />
        </group>
      </group>

      <group position={[X_NOW, disp(S_NOW) * PH, 0]}>
        <group ref={markG} scale={0.001}>
          <mesh>
            <sphereGeometry args={[0.07, 16, 16]} />
            <meshBasicMaterial color="#ffffff" />
          </mesh>
          <mesh>
            <ringGeometry args={[0.13, 0.16, 32]} />
            <meshBasicMaterial color="#ffffff" transparent opacity={0.7} side={DoubleSide} />
          </mesh>
        </group>
      </group>

      <Html position={[PW * 0.2, disp(0.2) * PH + 0.25, 0]} center zIndexRange={[5, 0]} style={{ pointerEvents: "none" }}>
        <div ref={setLabel(0)} className={labelCls} style={{ color: "#7dd3fc" }}>Historical observations</div>
      </Html>
      <Html position={[X_NOW, disp(S_NOW) * PH + 0.3, 0]} center zIndexRange={[5, 0]} style={{ pointerEvents: "none" }}>
        <div ref={setLabel(1)} className={labelCls} style={{ color: "#ffffff" }}>Current deformation</div>
      </Html>
      <Html position={[PW * 0.78, disp(0.78) * PH + 0.45, 0]} center zIndexRange={[5, 0]} style={{ pointerEvents: "none" }}>
        <div ref={setLabel(2)} className={labelCls} style={{ color: "#ffb15c" }}>Predicted movement</div>
      </Html>
      <Html position={[PW * 1.0 + 0.55, disp(1) * PH - 0.1, 0]} center zIndexRange={[5, 0]} style={{ pointerEvents: "none" }}>
        <div ref={setLabel(3)} className={labelCls} style={{ color: "#ff9d4d" }}>Prediction uncertainty</div>
      </Html>
    </group>
  );
}
