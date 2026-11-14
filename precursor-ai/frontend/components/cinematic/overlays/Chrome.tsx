/** Persistent hero UI: honesty footnote and scroll hint. Brand, nav and page progress live in landing/SiteNav. */
export function Chrome() {
  return (
    <>
      <p
        data-scroll-hint
        className="pointer-events-none absolute inset-x-0 bottom-14 z-10 text-center md:bottom-6 font-mono text-[10px] uppercase tracking-[0.35em] text-ink-muted"
      >
        Scroll
      </p>

      <p className="pointer-events-none absolute bottom-3 right-6 z-10 max-w-[18rem] text-right text-[10px] leading-snug text-ink-muted md:right-16 md:max-w-md">
        Illustrative visualization: decorative Earth imagery and synthetic data. Not NASA, NISAR or Sentinel-1 measurements.
      </p>
    </>
  );
}
