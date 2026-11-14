"use client";

import { ClipboardCheck } from "lucide-react";
import { DataTable, type Column } from "@/components/dashboard/data-table";
import { EmptyState } from "@/components/dashboard/empty-state";
import { ErrorState } from "@/components/dashboard/error-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { AlertBlock, Notice } from "@/components/data/badges";
import { Card, CardContent } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { splitValues } from "@/lib/environmental-helpers";
import { getQualityReport } from "@/services/environmental";

const strings = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

export function QualityTab({ areaId }: { areaId: string }) {
  const q = useApi((s) => getQualityReport(areaId, s));
  if (q.isLoading && !q.data) return <LoadingState label="Loading quality report" />;
  if (q.error) return <ErrorState title="Could not load quality report" message={q.error.message} onRetry={q.refetch} />;
  const report = q.data?.report ?? {};
  if (!q.data || Object.keys(report).length === 0) {
    return <EmptyState icon={ClipboardCheck} title="No quality report" description="No quality report exists for this area yet. Process the area from the Overview tab." />;
  }
  // The report is a free-form dict in the API contract: show scalar fields generically, lists of strings as alerts.
  const { stats } = splitValues(report);
  const warnings = strings(report.warnings);
  const checks = (k: string) => strings(report[k]);
  const cols: Column<(typeof stats)[number]>[] = [
    { key: "k", header: "Field", render: (s) => <span className="font-mono text-xs text-ink">{s.key}</span> },
    { key: "v", header: "Value", render: (s) => (s.value === null ? "n/a" : String(s.value)) },
  ];
  return (
    <div className="space-y-4">
      <Notice>
        Validation status: NOT_VALIDATED. File integrity and processing success are not scientific validation. Passed checks mean the pipeline ran, not that values are correct.
      </Notice>
      <AlertBlock title="Warnings" items={warnings} />
      <AlertBlock title="Failed checks" tone="danger" items={checks("failed_checks")} />
      {checks("passed_checks").length > 0 && (
        <Card><CardContent className="text-sm"><p className="font-medium">Passed checks</p>
          <ul className="mt-1 list-disc pl-6 text-ink-muted">{checks("passed_checks").map((c) => <li key={c}>{c}</li>)}</ul></CardContent></Card>
      )}
      <Card><CardContent>
        <DataTable caption="Quality report fields (coverage, CRS, resolution, temporal range)" columns={cols} rows={stats} rowKey={(s) => s.key} emptyMessage="No scalar fields reported." />
      </CardContent></Card>
    </div>
  );
}
