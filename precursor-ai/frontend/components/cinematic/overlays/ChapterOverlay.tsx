import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { CHAPTERS } from "../animations/chapters";
import { cn } from "@/lib/utils";
import { scrollToSection } from "@/components/landing/scroller";

/** Text layer. Visibility is controlled ONLY by the master timeline (via data-chapter). */
export function ChapterOverlay() {
  return (
    <div className="pointer-events-none absolute inset-0 z-10">
      {CHAPTERS.map((c, i) => {
        const last = i === CHAPTERS.length - 1;
        return (
          <section
            key={c.id}
            data-chapter={c.id}
            aria-label={c.title}
            className={cn(
              "absolute px-6 [text-shadow:0_2px_28px_rgba(2,4,10,0.9)] md:px-16",
              c.align === "center"
                ? "inset-x-0 bottom-[16vh] mx-auto max-w-5xl text-center"
                : "bottom-[16vh] left-0 max-w-xl text-left",
            )}
            style={i === 0 ? undefined : { visibility: "hidden", opacity: 0 }}
          >
            <p className="mb-4 font-mono text-[11px] uppercase tracking-[0.3em] text-accent">{c.kicker}</p>
            {i === 0 ? (
              <h1 className="text-[clamp(1.7rem,4.2vw,3.6rem)] font-light uppercase leading-[1.1] tracking-[0.1em]">
                {c.title}
              </h1>
            ) : (
              <h2
                className={cn(
                  "font-light uppercase leading-[1.1] tracking-[0.1em]",
                  last ? "whitespace-nowrap text-[clamp(1.8rem,6vw,4.6rem)] tracking-[0.2em]" : "text-[clamp(1.5rem,3.4vw,2.8rem)]",
                )}
              >
                {c.title}
              </h2>
            )}
            <p className="mt-4 text-sm text-ink-muted md:text-base">{c.subtitle}</p>
            {i === 0 && (
              <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
                <Link
                  href="/dashboard"
                  className="pointer-events-auto inline-flex items-center gap-3 border border-accent/60 bg-accent/10 px-6 py-3 font-mono text-xs uppercase tracking-[0.25em] text-accent transition-colors hover:bg-accent hover:text-canvas"
                >
                  Open dashboard
                  <ArrowRight aria-hidden className="h-4 w-4" />
                </Link>
                <a
                  href="#about"
                  onClick={(e) => {
                    e.preventDefault();
                    history.pushState(null, "", "#about");
                    scrollToSection("about");
                  }}
                  className="pointer-events-auto px-4 py-3 font-mono text-xs uppercase tracking-[0.25em] text-ink transition-colors hover:text-accent"
                >
                  About the project
                </a>
              </div>
            )}
            {last && (
              <Link
                href="/dashboard"
                className="pointer-events-auto mt-8 inline-flex items-center gap-3 border border-accent/60 bg-accent/10 px-6 py-3 font-mono text-xs uppercase tracking-[0.25em] text-accent transition-colors hover:bg-accent hover:text-canvas"
              >
                Explore the platform
                <ArrowRight aria-hidden className="h-4 w-4" />
              </Link>
            )}
          </section>
        );
      })}
    </div>
  );
}
