"use client";

import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import { AdditiveBlending, BackSide, Mesh, ShaderMaterial, SphereGeometry, SRGBColorSpace, ImageBitmapLoader, Texture } from "three";
import { smooth } from "../utils/math";
import { progress } from "../animations/progress";
import { ATMOS_FRAG, ATMOS_VERT, CLOUD_FRAG, EARTH_FRAG, EARTH_VERT } from "../shaders/earth";
import { EARTH_R, SUN_DIR } from "../utils/geo";

/** Procedural Earth surface + cloud layer. Radar-data mode (uData) is driven by scroll. */
export function EarthGlobe({ segments }: { segments: number }) {
  const cloudRef = useRef<Mesh>(null);

  const { geo, cloudGeo, earthMat, cloudMat } = useMemo(() => {
    const sun = { value: SUN_DIR };
    return {
      geo: new SphereGeometry(EARTH_R, segments, segments),
      cloudGeo: new SphereGeometry(EARTH_R * 1.012, Math.round(segments * 0.75), Math.round(segments * 0.75)),
      earthMat: new ShaderMaterial({
        vertexShader: EARTH_VERT,
        fragmentShader: EARTH_FRAG,
        uniforms: { uSun: sun, uData: { value: 0 }, uTex: { value: 0 }, uAlbedo: { value: null }, uMask: { value: null }, uBump: { value: null }, uNight: { value: null } },
      }),
      cloudMat: new ShaderMaterial({
        vertexShader: EARTH_VERT,
        fragmentShader: CLOUD_FRAG,
        transparent: true,
        depthWrite: false,
        uniforms: { uSun: sun, uTime: { value: 0 }, uFade: { value: 1 }, uTex: { value: 0 }, uClouds: { value: null } },
      }),
    };
  }, [segments]);

  // Real Earth textures (59-earth, downsized to /public/textures/earth). The procedural globe shows until all load.
  // Decoded off the main thread (ImageBitmap) and uploaded to the GPU one per tick, so the hero never janks.
  const gl = useThree((s) => s.gl);
  useEffect(() => {
    let cancelled = false;
    const loader = new ImageBitmapLoader().setOptions({ imageOrientation: "flipY", premultiplyAlpha: "none" });
    const tick = () => new Promise((r) => setTimeout(r, 60));
    const load = async (name: string, srgb: boolean) => {
      const bmp = await loader.loadAsync(`/textures/earth/${name}.jpg`);
      const t = new Texture(bmp);
      t.flipY = false;
      t.needsUpdate = true;
      if (srgb) t.colorSpace = SRGBColorSpace;
      t.anisotropy = Math.min(8, gl.capabilities.getMaxAnisotropy());
      if (cancelled) return t.dispose();
      loaded.current.push(t);
      gl.initTexture(t); // upload now, alone
      await tick();
      return t;
    };
    const start = setTimeout(() => {
     (async () => {
      const albedo = await load("albedo", true);
      const mask = await load("mask", false);
      const bump = await load("bump", false);
      const night = await load("night", false);
      const clouds = await load("clouds", false);
      if (cancelled || !albedo || !mask || !bump || !night || !clouds) return;
      Object.assign(earthMat.uniforms, {
        uAlbedo: { value: albedo }, uMask: { value: mask }, uBump: { value: bump }, uNight: { value: night }, uTex: { value: 1 },
      });
      Object.assign(cloudMat.uniforms, { uClouds: { value: clouds }, uTex: { value: 1 } });
    })().catch((e) => console.warn("Earth textures failed; keeping procedural globe", e));
    }, 2000); // progressive enhancement: let hydration and first render finish first
    return () => {
      cancelled = true;
      clearTimeout(start);
      loaded.current.forEach((t) => t.dispose());
      loaded.current = [];
    };
  }, [earthMat, cloudMat, gl]);
  const loaded = useRef<Texture[]>([]);

  useEffect(
    () => () => {
      geo.dispose();
      cloudGeo.dispose();
      earthMat.dispose();
      cloudMat.dispose();
    },
    [geo, cloudGeo, earthMat, cloudMat],
  );

  useFrame(({ clock }) => {
    const p = progress.p;
    earthMat.uniforms.uData.value = smooth(0.3, 0.46, p);
    cloudMat.uniforms.uFade.value = 1 - smooth(0.28, 0.4, p);
    cloudMat.uniforms.uTime.value = clock.elapsedTime;
    if (cloudRef.current) {
      cloudRef.current.visible = cloudMat.uniforms.uFade.value > 0.01;
      cloudRef.current.rotation.y = clock.elapsedTime * 0.006;
    }
  });

  return (
    <>
      <mesh geometry={geo} material={earthMat} />
      <mesh ref={cloudRef} geometry={cloudGeo} material={cloudMat} />
    </>
  );
}

export function EarthAtmosphere({ segments }: { segments: number }) {
  const { geo, mat } = useMemo(
    () => ({
      geo: new SphereGeometry(EARTH_R * 1.14, segments, segments),
      mat: new ShaderMaterial({
        vertexShader: ATMOS_VERT,
        fragmentShader: ATMOS_FRAG,
        side: BackSide,
        transparent: true,
        depthWrite: false,
        blending: AdditiveBlending,
        uniforms: { uSun: { value: SUN_DIR }, uFade: { value: 1 } },
      }),
    }),
    [segments],
  );

  useEffect(
    () => () => {
      geo.dispose();
      mat.dispose();
    },
    [geo, mat],
  );

  useFrame(() => {
    mat.uniforms.uFade.value = 1 - 0.6 * smooth(0.4, 0.6, progress.p);
  });

  return <mesh geometry={geo} material={mat} />;
}
