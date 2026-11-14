"use client";

import { Canvas } from "@react-three/fiber";
import { Starfield } from "../objects/Starfield";
import { CameraController } from "./CameraController";
import { EarthScene } from "./EarthScene";
import { SatelliteScene } from "./SatelliteScene";

export default function CinematicCanvas({ mobile }: { mobile: boolean }) {
  return (
    <Canvas
      dpr={mobile ? [1, 1.25] : [1, 1.75]}
      camera={{ fov: 42, near: 0.1, far: 500, position: [-8, 6, 64] }}
      gl={{ antialias: !mobile, powerPreference: "high-performance", alpha: false }}
    >
      <color attach="background" args={["#02040a"]} />
      <ambientLight intensity={0.15} />
      <directionalLight position={[60, 24, 80]} intensity={3} />
      <CameraController mobile={mobile} />
      <Starfield count={mobile ? 1500 : 4000} />
      <EarthScene mobile={mobile} />
      <SatelliteScene mobile={mobile} />
    </Canvas>
  );
}
