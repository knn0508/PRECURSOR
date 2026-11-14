# Cinematic landing page (`/`)

A single pinned, scroll-scrubbed 3D journey: Earth -> SAR satellite -> SAR/InSAR terrain -> forecast -> PRECURSOR AI. The CTA links to `/dashboard`; a "Dashboard" link is always visible.

**Everything shown is illustrative.** The Earth is procedural, the terrain, deformation field, trajectory and risk heatmap are synthetic, and the radar effects are artistic. None of it is a NASA, NISAR or Sentinel-1 measurement or a model output, and the page says so on screen.

## Architecture (`frontend/components/cinematic/`)

| Folder | Role |
|---|---|
| `animations/` | `progress.ts` (shared scroll progress 0..1), `chapters.ts` (text + ranges), `cameraPath.ts` (keyframed Catmull-Rom camera) |
| `hooks/` | `useScrollTimeline` (Lenis + the ONE GSAP timeline), `useCinematicEnv` (WebGL / reduced-motion / mobile) |
| `scenes/` | `CinematicCanvas`, `EarthScene`, `SatelliteScene`, `TerrainScene`, `CameraController` |
| `objects/` | `EarthGlobe` (+ clouds, `EarthAtmosphere`), `SatelliteModel`, `TerrainModel`, `Starfield` |
| `effects/` | `SatelliteOrbit`, `RadarBeam`, `RadarWaves`, `ParticleField`, `DeformationLayer`, `RiskHeatmap` |
| `shaders/` | GLSL: Earth, clouds, atmosphere, radar beam/waves/particles, terrain (SAR -> interferogram -> elevation + contours), heatmap |
| `overlays/` | DOM text, HUD, persistent chrome, static fallback |
| `utils/` | math, globe/patch geometry, procedural terrain |

### One continuous journey
`useScrollTimeline` creates one GSAP timeline with one pinned ScrollTrigger (`scrub: 1`). It tweens `progress.p` from 0 to 1 and fades the DOM text/HUD at fixed positions on the same timeline. Every 3D object and the camera read `progress.p` inside `useFrame`, so scrolling causes no React re-renders and there is no second ScrollTrigger to conflict. Cleanup (`ctx.revert()`, ticker removal, `lenis.destroy()`) runs on unmount.

### Chapters

| Progress | Chapter | What happens |
|---|---|---|
| 0.00-0.15 | Earth | far shot, slow spin, atmosphere, clouds, stars; dolly in |
| 0.15-0.35 | Observation | satellite enters from the limb on an inclined orbit; side-looking beam, ground rings, data particles |
| 0.35-0.55 | SAR / InSAR | globe darkens into a radar graticule; camera descends; patch shows SAR speckle raster, scan line, then interferogram-style fringes and a coherence mask |
| 0.55-0.80 | Prediction | relief and displacement rise, cyan elevation / orange deformation contours, risk heatmap, 3D time-series split into historical / current / predicted / uncertainty |
| 0.80-1.00 | Reveal | camera pulls back, relief flattens into a classed risk map, HUD and CTA appear |

## Assets
The Earth uses the user-supplied `59-earth/` texture pack (albedo, land/ocean mask, bump, night lights, clouds), downsized with PIL to `frontend/public/textures/earth/` (all 2048x1024: `albedo.jpg` RGB, the other four greyscale; about 1.2 MB total instead of about 22 MB; the `.blend` is not used because browsers cannot load it). They are loaded in `EarthGlobe` 2 s after the globe mounts (progressive enhancement), decoded off-thread (`ImageBitmapLoader`) and uploaded one per tick; until all five arrive the old procedural globe shows (`uTex` 0 -> 1). Mask drives ocean glint, bump drives shading, night lights show on the dark side, clouds replace the procedural cloud noise. **Licence/provenance of the pack is UNKNOWN (no licence file); confirm its terms before any public release.** Atmosphere, satellite (generic radar bus) and terrain remain procedural.

## Performance
- Earth textures (about 1.2 MB) load 2 s after the canvas mounts; failure keeps the procedural globe. Measured: loading them immediately raised Lighthouse TBT from ~340 ms to 1.6-2.2 s (4096 albedo) / 0.7-0.85 s (2048 albedo); with the 2 s delay TBT is 370 ms and performance 0.78, same as before. The delay moves the cost after the measured window, it does not remove it; GPU upload cost on real devices is NOT measured.
- Three.js is dynamically imported (`ssr: false`) and only fetched when the experience renders.
- DPR capped at 1.75 (1.25 mobile). Mobile: 64-segment globe, 72-segment terrain, 120 particles, 1500 stars, 450% scroll length (700% desktop), no pointer parallax.
- One draw call for all particles (GPU-animated); terrain and heatmap share one geometry; no post-processing.
- Geometries/materials created in `useMemo` are disposed on unmount.
- `frameloop` is always on (the scene animates continuously).

## Fallbacks
- No WebGL, `prefers-reduced-motion`, or a render error: `StaticFallback` (same five chapters as plain sections, no animation, no scroll hijack).

## Known limitations
- The hero (cinematic) is client-rendered, so its headline is not in the initial HTML; the About, Services, Contact and Footer sections are server-rendered.
- No bloom or real shadows; glow is shader-based.
- Satellite, orbit and patch are not to scale (exaggerated for legibility).
- Visually verified with software GL in headless Chrome (desktop and a phone-size viewport), not on real GPUs or touch devices; frame rate was not measured.
- Chrome logs one `THREE.Clock deprecated` warning from inside `@react-three/fiber`.
- Camera keyframes use uniform Catmull-Rom, so speed varies slightly per chapter.
- Pointer parallax is small and desktop-only.

## Content sections and transitions (`frontend/components/landing/`)

After the pinned hero (`#home`) the page continues in normal flow: `#about`, `#services`, `#contact`, then the footer. There is no second pin (touch scrolling stays native below the hero). Section copy is server-rendered; Services cards come from `status.ts`, whose chips mirror [PROJECT_STATUS](project/PROJECT_STATUS.md) (implemented-synthetic / mock-tested / partial / planned). Contact has no form: a `mailto:` link, with placeholder email, GitHub and team-page links clearly marked. Hero and chapter copy no longer claims AI forecasting; early prediction is described as a research goal with no ML model.

| File | Role |
|---|---|
| `sections.ts` | anchor map, `activeSection()` (last section past 40% of the viewport; last one at page bottom), `hashToSectionId()` |
| `status.ts` | status-chip mapping and the seven capabilities |
| `scroller.ts` | holds the hero's Lenis instance; `scrollToSection()` (Lenis if present, else instant native jump) |
| `SiteNav.tsx` | fixed header, active tracking (rAF-throttled scroll listener), hash sync (`pushState` on click, debounced `replaceState` on scroll, `popstate` handler), page progress bar, mobile menu, skip link, deep-link settling for `/#contact` |
| `Reveal.tsx` | the section transition |
| `ContentSections.tsx` | About, Services, Contact, Footer |

**One transition language** (`Reveal.tsx`): elements marked `data-reveal` fade up (opacity + translateY 24px, 0.8s `power2.out`, 70ms stagger, one-shot) and `data-rule` hairlines draw across (scaleX) at each section top. About starts on a gradient from the hero's `#02040a` into the canvas colour. The global progress bar (header bottom edge) and active-nav highlight complete it. Only transform/opacity is animated. The hero pin uses `refreshPriority: 1` so its spacer is laid out before the reveal triggers.

**Reduced motion / no WebGL:** `Reveal` does nothing (all content visible), anchor jumps are instant native scrolls, there is no Lenis and no pin. The hero becomes `StaticFallback` (same chapters, plus an About link).

**Verified (headless Chrome via playwright-core, software GL, 2026-11-14):** desktop 1440x900, phone 375x812 touch, desktop reduced-motion. All four nav anchors land on their section with the right active item and hash; back/forward restore position; `/#contact` deep link lands; no horizontal overflow; one h1, one main, header, footer; no console errors besides the existing THREE.Clock deprecation and SwiftShader GL notices. Lighthouse (production build, simulated throttling, 2 runs each): performance 0.78/0.80 before, 0.79/0.79 after; CLS 0 both; FCP 1.3s to 0.8s; LCP 4.0s and TBT 330-370ms unchanged; accessibility 1.00 after (not measured before). Not verified: real GPU frame rate, real touch devices, Safari/Firefox, screen readers.
