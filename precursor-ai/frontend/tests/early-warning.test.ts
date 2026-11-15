import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { EarlyWarningSwitch } from "@/components/workspace/early-warning-panel";
import { MockBanner, MockView, NotAvailableView } from "@/components/workspace/early-warning-views";
import { SourceBadge } from "@/components/workspace/source-badge";
import { resolveView } from "@/lib/early-warning";
import { MOCK_BANNER_TEXT, MOCK_SEED, mockContributions, mockSusceptibilityGrid, mockTriggerSeries, neutralRamp } from "@/lib/mock-predictions";
import { EXPLAIN_OK, NOT_TRAINED, OK_RESPONSE, TEST_FIXTURE } from "./fixtures/prediction-fixtures";

const html = (head: "susceptibility" | "trigger", response: typeof NOT_TRAINED | null, flag: boolean, extra = {}) =>
  renderToStaticMarkup(createElement(EarlyWarningSwitch, { head, response, mockFlag: flag, ...extra }));

describe("view resolution", () => {
  it("is N/A by default, MOCK only with the flag, REAL as soon as the API answers OK", () => {
    expect(resolveView(NOT_TRAINED, false)).toBe("NA");
    expect(resolveView(null, false)).toBe("NA");
    expect(resolveView(NOT_TRAINED, true)).toBe("MOCK");
    expect(resolveView(OK_RESPONSE, false)).toBe("REAL");
    expect(resolveView(OK_RESPONSE, true)).toBe("REAL"); // real output always beats mock
    expect(resolveView({ ...OK_RESPONSE, output: null }, false)).toBe("NA"); // OK without output is not a prediction
  });
});

describe("mock views always carry the banner and badge, and vanish with the flag off", () => {
  for (const head of ["susceptibility", "trigger"] as const) {
    it(`mock ${head}: banner, badge, watermark, no export control`, () => {
      const m = html(head, NOT_TRAINED, true);
      expect(m).toContain(MOCK_BANNER_TEXT);
      expect(m).toContain("data-mock-banner");
      expect(m).toContain("data-mock-badge");
      expect(m).toContain("Research prototype, not an official warning");
      expect(m).not.toMatch(/download=|<a |href=|<button/i); // nothing in the mock view can export or navigate
    });
    it(`flag off ${head}: no mock content at all, only N/A`, () => {
      const n = html(head, NOT_TRAINED, false);
      expect(n).toContain("N/A");
      expect(n).toContain("N/A until a real, validated source exists");
      expect(n).not.toMatch(/mock/i);
      expect(n).not.toContain('role="img"'); // no chart or map graphic (the notice icon is decorative)
    });
  }
  it("the banner component itself is the exact required text", () => {
    expect(renderToStaticMarkup(createElement(MockBanner))).toContain("MOCK DATA: NOT A PREDICTION");
  });
  it("mock trigger view with a slider is keyboard-operable (range input with a label)", () => {
    const m = renderToStaticMarkup(createElement(MockView, { head: "trigger", seed: MOCK_SEED, day: 3, onDay: () => {} }));
    expect(m).toMatch(/<label[^>]*for="mock-day"/);
    expect(m).toContain('type="range"');
  });
});

describe("mock styling avoids risk semantics", () => {
  it("uses no red/amber/green utility classes in any mock markup", () => {
    for (const head of ["susceptibility", "trigger"] as const) {
      const m = html(head, NOT_TRAINED, true);
      expect(m).not.toMatch(/(text|bg|border|fill|stroke)-(red|amber|yellow|orange|green|emerald|lime|ok|warn|danger)/);
    }
  });
  it("the ramp is neutral: channels stay close together (no hue), low to high", () => {
    for (let v = 0; v <= 1; v += 0.1) {
      const [r, g, b] = neutralRamp(v).match(/\d+/g)!.map(Number);
      expect(Math.max(r, g, b) - Math.min(r, g, b)).toBeLessThanOrEqual(25);
    }
  });
});

describe("mock generators", () => {
  it("are deterministic for a seed, bounded, take no real input and are tagged mock", () => {
    expect(mockSusceptibilityGrid(MOCK_SEED)).toEqual(mockSusceptibilityGrid(MOCK_SEED));
    expect(mockSusceptibilityGrid(1).values).not.toEqual(mockSusceptibilityGrid(2).values);
    const g = mockSusceptibilityGrid(MOCK_SEED, 20, 20);
    expect(g.mock).toBe(true);
    expect(g.values).toHaveLength(400);
    expect(g.values.every((v) => v >= 0 && v <= 1)).toBe(true);
    const t = mockTriggerSeries(MOCK_SEED);
    expect(t.mock).toBe(true);
    expect(t.values.every((v) => v >= 0 && v <= 1)).toBe(true);
    expect(mockContributions(MOCK_SEED).every((c) => c.mock && c.feature.startsWith("mock_feature_"))).toBe(true);
    // generators accept only numbers: there is no parameter through which a real value could enter
    expect(mockSusceptibilityGrid.length).toBeLessThanOrEqual(3);
  });
});

describe("real-response path (TEST_FIXTURE)", () => {
  it("activates automatically on OK, with no mock banner even when the flag is on", () => {
    const r = html("susceptibility", OK_RESPONSE, true, { explainResponse: EXPLAIN_OK, modelCardPath: "models/x/1/MODEL_CARD.md" });
    expect(r).toContain('data-view="real"');
    expect(r).toContain("50.0%");
    expect(r).toContain(TEST_FIXTURE);
    expect(r).toContain("NOT calibrated");
    expect(r).toContain("Valid time: 2020-01-01T00:00:00Z");
    expect(r).toContain("test_feature");
    expect(r).toContain("not physical causation");
    expect(r).toContain("models/x/1/MODEL_CARD.md");
    expect(r).toContain("MODEL PREDICTION");
    expect(r).not.toContain("data-mock-banner");
    expect(r).toContain("Research prototype, not an official warning");
  });
  it("states calibration only when the response does", () => {
    const calibrated = { ...OK_RESPONSE, output: { ...OK_RESPONSE.output!, calibration: { calibrated: true, method: "isotonic", reference: null } } };
    const r = html("susceptibility", calibrated, false);
    expect(r).toContain("Calibrated (isotonic)");
    expect(r).not.toContain("NOT calibrated");
  });
  it("shows explanation unavailable when the API says so", () => {
    const r = html("susceptibility", OK_RESPONSE, false, { explainResponse: { status: "MODEL_NOT_AVAILABLE", message: "x", explanation: null } });
    expect(r).toContain("Explanation: not available for this model");
  });
});

describe("source badges", () => {
  it("render the exact kind and a description", () => {
    const m = renderToStaticMarkup(createElement(SourceBadge, { kind: "SYNTHETIC_DEMO" }));
    expect(m).toContain("SYNTHETIC DEMO");
    expect(m).toContain('data-source-kind="SYNTHETIC_DEMO"');
    expect(m).toContain("not a real measurement");
  });
  it("the not-available view is badged PLACEHOLDER", () => {
    expect(renderToStaticMarkup(createElement(NotAvailableView, { head: "trigger" }))).toContain("PLACEHOLDER");
  });
});
