"use client";

import { useState } from "react";
import { ErrorState } from "@/components/dashboard/error-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { MockView, NotAvailableView, RealView } from "@/components/workspace/early-warning-views";
import { useApi } from "@/hooks/use-api";
import { USE_MOCK_PREDICTIONS } from "@/lib/config";
import { resolveView } from "@/lib/early-warning";
import { MOCK_SEED } from "@/lib/mock-predictions";
import { explain, getUncertaintyReport, predict } from "@/services/prediction";
import type { ExplainResponse, Head, PredictionResponse, UncertaintyReport } from "@/types/prediction";

/** Pure switch (testable): picks the view from the API response and the flag. REAL wins whenever the API returns OK. */
export function EarlyWarningSwitch({ head, response, mockFlag, explainResponse = null, uncertainty = null, modelCardPath = null, day = 0, onDay }: {
  head: Head; response: PredictionResponse | null; mockFlag: boolean; explainResponse?: ExplainResponse | null; uncertainty?: UncertaintyReport | null;
  modelCardPath?: string | null; day?: number; onDay?: (d: number) => void;
}) {
  const view = resolveView(response, mockFlag);
  if (view === "REAL" && response) return <RealView response={response} explain={explainResponse} uncertainty={uncertainty} modelCardPath={modelCardPath} />;
  if (view === "MOCK") return <MockView head={head} seed={MOCK_SEED} day={day} onDay={onDay} />;
  return <NotAvailableView head={head} message={response?.message} />;
}

function RealLoader({ areaId, response, head }: { areaId: string; response: PredictionResponse; head: Head }) {
  const ex = useApi((s) => explain({ area_id: areaId, head, scope: "global" }, s).catch(() => null));
  const un = useApi((s) => getUncertaintyReport(areaId, s).catch(() => null));
  return <EarlyWarningSwitch head={head} response={response} mockFlag={false} explainResponse={ex.data} uncertainty={un.data} />;
}

export function EarlyWarningPanel({ areaId, head }: { areaId: string; head: Head }) {
  const [day, setDay] = useState(0);
  const r = useApi((s) => predict(head, { area_id: areaId }, s));
  if (r.isLoading && !r.data) return <LoadingState label="Asking the prediction API" />;
  if (r.error) return <ErrorState title="Could not reach the prediction API" message={r.error.message} onRetry={r.refetch} />;
  if (r.data?.status === "OK" && r.data.output) return <RealLoader areaId={areaId} response={r.data} head={head} />;
  return <EarlyWarningSwitch head={head} response={r.data} mockFlag={USE_MOCK_PREDICTIONS} day={day} onDay={setDay} />;
}
