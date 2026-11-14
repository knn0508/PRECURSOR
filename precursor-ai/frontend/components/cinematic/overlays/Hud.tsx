/** Scene 4/5 interface elements. Shown/hidden by the master timeline (data-hud). */
const SWATCH = [
  { c: "#38bdf8", t: "Historical observations" },
  { c: "#ffffff", t: "Current deformation" },
  { c: "#ff8a1f", t: "Predicted movement" },
  { c: "rgba(255,138,31,0.35)", t: "Prediction uncertainty" },
];

export function Hud() {
  return (
    <div className="pointer-events-none absolute inset-0 z-10" aria-hidden>
      <div
        data-hud="legend"
        className="absolute right-6 top-20 space-y-2 border-l border-line pl-4 font-mono text-[10px] uppercase tracking-[0.18em] text-ink-muted md:right-16"
        style={{ visibility: "hidden", opacity: 0 }}
      >
        <p className="text-ink-faint">Illustrative legend</p>
        {SWATCH.map((s) => (
          <p key={s.t} className="flex items-center gap-2">
            <span className="h-[2px] w-5" style={{ background: s.c }} />
            {s.t}
          </p>
        ))}
      </div>

      <div data-hud="map" className="absolute inset-0" style={{ visibility: "hidden", opacity: 0 }}>
        {["left-5 top-16 border-l border-t", "right-5 top-16 border-r border-t", "bottom-14 left-5 border-b border-l", "bottom-14 right-5 border-b border-r"].map(
          (cls) => (
            <span key={cls} className={`absolute h-6 w-6 border-accent/60 ${cls}`} />
          ),
        )}
        <div className="absolute right-6 top-20 w-44 font-mono text-[10px] uppercase tracking-[0.18em] text-ink-muted md:right-16">
          <p className="mb-2 text-ink-faint">Illustrative synthetic score</p>
          <div
            className="h-2 w-full"
            style={{ background: "linear-gradient(90deg,#0c1d2e,#ffb81f,#ff6a0d,#f21f1a)" }}
          />
          <div className="mt-1 flex justify-between">
            <span>Low</span>
            <span>High</span>
          </div>
          <p className="mt-3 normal-case tracking-normal text-ink-faint">
            Synthetic demo layer. Not a calibrated probability.
          </p>
        </div>
      </div>
    </div>
  );
}
