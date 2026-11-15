"use client";

import { ErrorState } from "@/components/dashboard/error-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { API_URL, USE_MOCK_PREDICTIONS } from "@/lib/config";
import { getHealth, getSystemInfo } from "@/services/system";
import { getDataStatus } from "@/services/data";
import { getPredictionStatus } from "@/services/prediction";

/** Read-only: every value comes from the running backend or the build configuration. Nothing here is editable. */
export function SettingsPage() {
  const sys = useApi((s) => getSystemInfo(s));
  const health = useApi((s) => getHealth(s));
  const data = useApi((s) => getDataStatus(s));
  const pred = useApi((s) => getPredictionStatus(s));
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Settings</h1>
        <p className="mt-1 text-sm text-ink-muted">Read-only view of the running configuration. Change it through environment variables and rebuild (see docs/development).</p>
      </div>
      <Card>
        <CardHeader><CardTitle>Connection</CardTitle></CardHeader>
        <CardContent>
          {sys.error ? <ErrorState title="Backend unreachable" message={sys.error.message} onRetry={sys.refetch} /> : !sys.data ? <LoadingState label="Loading" /> : (
            <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
              <div><dt className="text-ink-muted">API URL</dt><dd className="break-all font-mono text-xs">{API_URL}</dd></div>
              <div><dt className="text-ink-muted">App / version</dt><dd>{sys.data.app_name} {sys.data.version}</dd></div>
              <div><dt className="text-ink-muted">Environment</dt><dd>{sys.data.environment}</dd></div>
              <div><dt className="text-ink-muted">Database</dt><dd>{health.data ? <Badge variant={health.data.database === "connected" ? "ok" : "demo"}>{health.data.database}</Badge> : "unknown"}</dd></div>
              <div><dt className="text-ink-muted">Earthdata credentials</dt><dd>{data.data ? (data.data.earthdata_credentials_configured ? "configured (never shown)" : "not configured") : "unknown"}</dd></div>
              <div><dt className="text-ink-muted">Data root</dt><dd className="font-mono text-xs">{data.data?.data_root ?? "unknown"}</dd></div>
            </dl>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Prediction policy</CardTitle></CardHeader>
        <CardContent className="space-y-1 text-sm">
          <p>Prediction backend: <strong>{pred.data?.backend ?? "unknown"}</strong> ({pred.data?.status ?? "unknown"}).</p>
          <p>Mock prediction views: <Badge variant={USE_MOCK_PREDICTIONS ? "demo" : "neutral"}>{USE_MOCK_PREDICTIONS ? "ON (labelled MOCK)" : "OFF"}</Badge> (build-time flag NEXT_PUBLIC_USE_MOCK_PREDICTIONS).</p>
          <p className="text-xs text-ink-muted">All forecasts are research outputs: inferred, not warnings, not probabilities.</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Platform modules</CardTitle></CardHeader>
        <CardContent>
          {!sys.data ? <LoadingState label="Loading" /> : (
            <ul className="divide-y divide-line text-sm">
              {sys.data.modules.map((m) => (
                <li key={m.name} className="flex items-center justify-between gap-3 py-2">
                  <span><strong>{m.name}</strong> <span className="text-ink-muted">{m.description}</span></span>
                  <Badge variant={m.status === "available" ? "ok" : "neutral"}>{m.status}</Badge>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
