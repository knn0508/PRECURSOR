"use client";

import { DataTable, type Column } from "@/components/dashboard/data-table";
import { DataKindBadge, MaturityBadge, StatusBadge } from "@/components/data/badges";
import { formatBytes } from "@/lib/data-helpers";
import { formatDateTime } from "@/lib/utils";
import type { GranuleResult } from "@/types/data";

interface Props {
  rows: GranuleResult[];
  caption: string;
  /** When set, registered rows get a checkbox. Unregistered (dry-run) rows are disabled. */
  selected?: Set<string>;
  onToggle?: (acquisitionId: string) => void;
}

export function GranuleTable({ rows, caption, selected, onToggle }: Props) {
  const cols: Column<GranuleResult>[] = [];
  if (selected && onToggle) {
    cols.push({
      key: "sel",
      header: "Select",
      render: (r) => (
        <input
          type="checkbox"
          aria-label={`Select ${r.granule_id} for download`}
          disabled={!r.registered || !r.acquisition_id}
          checked={!!r.acquisition_id && selected.has(r.acquisition_id)}
          onChange={() => r.acquisition_id && onToggle(r.acquisition_id)}
        />
      ),
    });
  }
  cols.push(
    { key: "id", header: "Granule", render: (r) => <span className="break-all font-mono text-xs text-ink">{r.granule_id}</span> },
    { key: "product", header: "Product", render: (r) => `${r.provider} ${r.product_type}` },
    { key: "acq", header: "Acquired", render: (r) => (r.acquisition_start ? formatDateTime(r.acquisition_start) : "unknown") },
    { key: "base", header: "Baseline (days)", render: (r) => r.temporal_baseline_days ?? "-" },
    { key: "orbit", header: "Orbit", render: (r) => [r.orbit_direction, r.relative_orbit].filter((x) => x != null).join(" ") || "-" },
    { key: "size", header: "Size", render: (r) => formatBytes(r.file_size_bytes) },
    { key: "mat", header: "Maturity", render: (r) => <MaturityBadge maturity={r.maturity} /> },
    { key: "kind", header: "Data", render: (r) => <DataKindBadge kind={r.data_kind} /> },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.registered ? r.status : "NOT REGISTERED"} /> },
  );
  return <DataTable caption={caption} columns={cols} rows={rows} rowKey={(r) => r.granule_id} emptyMessage="No granules matched." />;
}
