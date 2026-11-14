import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { CHAPTERS } from "../animations/chapters";

/** No-WebGL / reduced-motion experience: same story, no animation, no scroll hijacking. */
export function StaticFallback({ reason }: { reason: string }) {
  return (
    <div
      className="min-h-screen px-6 pb-16 pt-28 md:px-16"
      style={{
        background:
          "radial-gradient(ellipse 90% 60% at 50% 115%, rgba(56,189,248,0.22), transparent 60%), radial-gradient(ellipse 60% 40% at 50% 100%, rgba(30,70,140,0.5), transparent 70%), #02040a",
      }}
    >
      <div className="mx-auto max-w-3xl space-y-16">
        <p className="font-mono text-[11px] uppercase tracking-[0.3em] text-ink-muted">PRECURSOR AI · {reason}</p>
        {CHAPTERS.map((c, i) => (
          <section key={c.id} aria-label={c.title}>
            <p className="mb-3 font-mono text-[11px] uppercase tracking-[0.3em] text-accent">{c.kicker}</p>
            {i === 0 ? (
              <h1 className="text-3xl font-light uppercase tracking-[0.1em] md:text-5xl">{c.title}</h1>
            ) : (
              <h2 className="text-2xl font-light uppercase tracking-[0.1em] md:text-4xl">{c.title}</h2>
            )}
            <p className="mt-3 text-ink-muted">{c.subtitle}</p>
          </section>
        ))}
        <a href="#about" className="block font-mono text-xs uppercase tracking-[0.25em] text-ink hover:text-accent">
          About the project
        </a>
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-3 border border-accent/60 bg-accent/10 px-6 py-3 font-mono text-xs uppercase tracking-[0.25em] text-accent hover:bg-accent hover:text-canvas"
        >
          Open dashboard
          <ArrowRight aria-hidden className="h-4 w-4" />
        </Link>
        <p className="text-xs text-ink-muted">
          Cinematic 3D journey unavailable. Illustrative content only; no real measurements are shown.
        </p>
      </div>
    </div>
  );
}
