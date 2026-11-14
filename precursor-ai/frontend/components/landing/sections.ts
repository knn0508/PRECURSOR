/** Single source of truth for landing-page sections (nav, anchors, active tracking). */
export const SECTIONS = [
  { id: "home", label: "Home" },
  { id: "about", label: "About" },
  { id: "services", label: "Services" },
  { id: "contact", label: "Contact" },
] as const;

export type SectionId = (typeof SECTIONS)[number]["id"];

export function isSectionId(value: string): value is SectionId {
  return SECTIONS.some((s) => s.id === value);
}

/** "#about" or "about" -> "about"; anything unknown -> "home". */
export function hashToSectionId(hash: string): SectionId {
  const id = hash.replace(/^#/, "");
  return isSectionId(id) ? id : "home";
}

/**
 * Active section from the viewport-relative top of each section.
 * The last section whose top has crossed `anchor` (fraction of viewport height) wins;
 * at the very bottom of the page the last section wins (a short final section may never cross).
 */
export function activeSection(
  tops: Partial<Record<SectionId, number>>,
  viewportHeight: number,
  atBottom = false,
  anchor = 0.4,
): SectionId {
  if (atBottom) return SECTIONS[SECTIONS.length - 1].id;
  let active: SectionId = "home";
  for (const s of SECTIONS) {
    const top = tops[s.id];
    if (top !== undefined && top <= viewportHeight * anchor) active = s.id;
  }
  return active;
}
