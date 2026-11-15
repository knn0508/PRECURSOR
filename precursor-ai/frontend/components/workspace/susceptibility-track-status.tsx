import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

// Snapshot of docs/ml/ML_STATUS.md as of 2026-11-15. Static on purpose: the ML track is deliberately not wired to the API (ADR-0009).
const STAGES: [string, string, "ok" | "demo"][] = [
  ["M1 to M4", "Problem, data discovery, acquisition (4.58 GB), preprocessing and cleaning on a 5 km grid: done", "ok"],
  ["M5", "Exploratory analysis on the training part of a sealed spatial hold-out: done. Verdict: susceptibility-only, small tabular models", "ok"],
  ["M6 to M9", "Features, baselines, evaluation, model card: not started, waiting for approval of a better label source (M5b)", "demo"],
];

export function SusceptibilityTrackStatus() {
  return (
    <Card>
      <CardHeader><CardTitle>Why there is no susceptibility map yet</CardTitle><Badge variant="demo">No model</Badge></CardHeader>
      <CardContent className="space-y-3 text-sm">
        <ul className="space-y-2">
          {STAGES.map(([k, v, t]) => (
            <li key={k} className="flex items-start gap-2"><Badge variant={t}>{k}</Badge><span className="text-ink-muted">{v}</span></li>
          ))}
        </ul>
        <p className="text-xs text-ink-muted">
          A map will appear only if a model beats the class-prior and few-feature baselines on the sealed hold-out with confidence intervals that exclude no-skill.
          Early finding: the strongest label signals are reporting proxies (e.g. built-up share), so not supported by these labels is an acceptable outcome.
          Details: docs/ml/ML_STATUS.md. For a real research output now, see Displacement Forecast.
        </p>
      </CardContent>
    </Card>
  );
}
