"use client";

import { Download } from "lucide-react";
import { useEffect, useState } from "react";
import { DataTable, type Column } from "@/components/dashboard/data-table";
import { EmptyState } from "@/components/dashboard/empty-state";
import { ErrorState } from "@/components/dashboard/error-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { StatusBadge } from "@/components/data/badges";
import { DataHeader } from "@/components/data/data-tabs";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { ApiError } from "@/lib/api-client";
import { formatBytes, hasActiveJobs, progressPercent } from "@/lib/data-helpers";
import { formatDateTime } from "@/lib/utils";
import { listDownloads, retryDownload } from "@/services/data";
import type { DownloadJobRead } from "@/types/data";

const POLL_MS = 3000;

/** Job table. Progress shows only the API's `progress` value. Retry column appears when `onRetry` is given. */
export function DownloadJobsList({ jobs, caption, onRetry, retrying }: {
  jobs: DownloadJobRead[]; caption: string; onRetry?: (id: string) => void; retrying?: string | null;
}) {
  const cols: Column<DownloadJobRead>[] = [
    { key: "g", header: "Granule", render: (j) => <span className="break-all font-mono text-xs text-ink">{j.granule_id ?? j.acquisition_id}</span> },
    { key: "p", header: "Product", render: (j) => j.product_type ?? "-" },
    { key: "s", header: "Status", render: (j) => <StatusBadge status={j.status} /> },
    {
      key: "prog",
      header: "Progress",
      render: (j) => (
        <div className="min-w-32">
          <div role="progressbar" aria-label={`Progress for ${j.granule_id ?? j.acquisition_id}`} aria-valuemin={0} aria-valuemax={100}
            aria-valuenow={progressPercent(j.progress)} className="h-2 overflow-hidden rounded bg-surface-2">
            <div className="h-full bg-accent" style={{ width: `${progressPercent(j.progress)}%` }} />
          </div>
          <span className="text-xs">{progressPercent(j.progress)}% ({formatBytes(j.bytes_downloaded)})</span>
        </div>
      ),
    },
    { key: "a", header: "Attempts", render: (j) => j.attempts },
    { key: "t", header: "Updated", render: (j) => formatDateTime(j.updated_at) },
    { key: "e", header: "Error", render: (j) => (j.error_message ? <span className="text-danger">{j.error_message}</span> : "-") },
  ];
  if (onRetry) {
    cols.push({
      key: "r",
      header: "Action",
      render: (j) =>
        j.status === "FAILED" ? (
          <Button size="sm" disabled={retrying === j.id} onClick={() => onRetry(j.id)}>
            {retrying === j.id ? "Retrying..." : "Retry"}
          </Button>
        ) : null,
    });
  }
  return <DataTable caption={caption} columns={cols} rows={jobs} rowKey={(j) => j.id} emptyMessage="No jobs." />;
}

export function DataDownloads() {
  const { data, error, isLoading, refetch } = useApi((s) => listDownloads({ limit: 100 }, s));
  const [retrying, setRetrying] = useState<string | null>(null);
  const [retryError, setRetryError] = useState<string | null>(null);

  // Poll only while something can still change; the timer is cleared on unmount or when jobs settle.
  useEffect(() => {
    if (!data || !hasActiveJobs(data.items)) return;
    const t = setTimeout(refetch, POLL_MS);
    return () => clearTimeout(t);
  }, [data, error, refetch]);

  async function retry(id: string) {
    setRetrying(id);
    setRetryError(null);
    try {
      await retryDownload(id);
      refetch();
    } catch (e) {
      setRetryError(e instanceof ApiError ? e.message : "Retry failed");
    } finally {
      setRetrying(null);
    }
  }

  const groups: [string, DownloadJobRead[]][] = data
    ? [
        ["Active", data.items.filter((j) => j.status === "QUEUED" || j.status === "RUNNING")],
        ["Failed", data.items.filter((j) => j.status === "FAILED")],
        ["Completed", data.items.filter((j) => j.status === "COMPLETED")],
      ]
    : [];

  return (
    <div className="space-y-6">
      <DataHeader title="Downloads" description="Download jobs and their real progress, refreshed every 3 seconds while any job is queued or running." />
      <div aria-live="polite">
        {isLoading && !data ? (
          <LoadingState label="Loading download jobs" />
        ) : error ? (
          <ErrorState title="Could not load download jobs" message={error.message} onRetry={refetch} />
        ) : null}
        {retryError && <ErrorState title="Retry failed" message={retryError} />}
      </div>
      {data && data.items.length === 0 && (
        <EmptyState icon={Download} title="No download jobs" description="Queue downloads from the Search tab. Downloads require an Earthdata login." />
      )}
      {groups.filter(([, js]) => js.length > 0).map(([title, js]) => (
        <section key={title} aria-label={`${title} jobs`} className="space-y-2">
          <h2 className="text-sm font-semibold">{title} ({js.length})</h2>
          <Card>
            <CardContent>
              <DownloadJobsList jobs={js} caption={`${title} download jobs`} onRetry={retry} retrying={retrying} />
            </CardContent>
          </Card>
        </section>
      ))}
    </div>
  );
}
