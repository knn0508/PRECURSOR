"use client";

import { MapPinned } from "lucide-react";
import { DataTable, type Column } from "@/components/dashboard/data-table";
import { EmptyState } from "@/components/dashboard/empty-state";
import { ErrorState } from "@/components/dashboard/error-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { Card, CardContent } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import { formatDateTime } from "@/lib/utils";
import { listAreas } from "@/services/areas";
import type { MonitoredArea } from "@/types/api";

const COLUMNS: Column<MonitoredArea>[] = [
  { key: "name", header: "Name", render: (r) => <span className="font-medium text-ink">{r.name}</span> },
  { key: "country", header: "Country", render: (r) => r.country ?? "-" },
  { key: "region", header: "Region", render: (r) => r.region ?? "-" },
  { key: "type", header: "Type", render: (r) => r.area_type },
  { key: "created", header: "Added", render: (r) => formatDateTime(r.created_at) },
];

export function AreasList() {
  const { data, error, isLoading, refetch } = useApi(listAreas);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Monitored Areas</h1>
        <p className="mt-1 text-sm text-ink-muted">Areas of interest registered in the database.</p>
      </div>
      {isLoading ? (
        <LoadingState label="Loading areas" />
      ) : error ? (
        <ErrorState title="Could not load areas" message={error.message} onRetry={refetch} />
      ) : data && data.items.length > 0 ? (
        <Card>
          <CardContent>
            <DataTable caption="Monitored areas" columns={COLUMNS} rows={data.items} rowKey={(r) => r.id} emptyMessage="" />
          </CardContent>
        </Card>
      ) : (
        <EmptyState
          icon={MapPinned}
          title="No monitored areas"
          description="Create areas through POST /api/v1/areas. A management UI comes in a later phase."
        />
      )}
    </div>
  );
}
