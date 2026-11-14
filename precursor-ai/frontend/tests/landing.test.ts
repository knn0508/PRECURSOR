import { describe, expect, it } from "vitest";
import { SECTIONS, activeSection, hashToSectionId, isSectionId } from "@/components/landing/sections";
import { CAPABILITIES, STATUS, statusInfo } from "@/components/landing/status";

describe("section map", () => {
  it("has unique ids, starting with home", () => {
    const ids = SECTIONS.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids[0]).toBe("home");
  });
  it("parses hashes, defaulting to home", () => {
    expect(hashToSectionId("#services")).toBe("services");
    expect(hashToSectionId("contact")).toBe("contact");
    expect(hashToSectionId("#nope")).toBe("home");
    expect(hashToSectionId("")).toBe("home");
    expect(isSectionId("about")).toBe(true);
    expect(isSectionId("footer")).toBe(false);
  });
});

describe("activeSection", () => {
  const vh = 1000;
  it("is home before About reaches the anchor line", () => {
    expect(activeSection({ home: -200, about: 900, services: 1800, contact: 2600 }, vh)).toBe("home");
  });
  it("switches when a section top crosses 40% of the viewport", () => {
    expect(activeSection({ home: -2000, about: 400, services: 1200, contact: 2000 }, vh)).toBe("about");
    expect(activeSection({ home: -2000, about: -600, services: 300, contact: 1100 }, vh)).toBe("services");
  });
  it("picks the last crossed section and handles missing elements", () => {
    expect(activeSection({ about: -100, services: -100 }, vh)).toBe("services");
    expect(activeSection({}, vh)).toBe("home");
  });
  it("returns the last section at the bottom of the page", () => {
    expect(activeSection({ home: -5000, about: -3000, services: -1000, contact: 700 }, vh, true)).toBe("contact");
  });
});

describe("status chips", () => {
  it("every capability has a known status with a text label", () => {
    for (const c of CAPABILITIES) {
      expect(STATUS[c.status]).toBeDefined();
      expect(statusInfo(c.status).label.length).toBeGreaterThan(0);
    }
  });
  it("covers the seven pipeline stages", () => {
    expect(CAPABILITIES).toHaveLength(7);
  });
  it("never claims prediction or explainability is implemented", () => {
    for (const id of ["prediction", "explainability"]) {
      expect(CAPABILITIES.find((c) => c.id === id)?.status).toBe("planned");
    }
  });
  it("copy makes no real-time / operational / accuracy claims", () => {
    const text = CAPABILITIES.map((c) => c.body).join(" ").toLowerCase();
    for (const banned of ["real-time", "operational", "accuracy", "%"]) expect(text).not.toContain(banned);
  });
});
