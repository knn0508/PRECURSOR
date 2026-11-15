"use client";

import { MapPinned } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { EmptyState } from "@/components/dashboard/empty-state";
import { ErrorState } from "@/components/dashboard/error-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { EarlyWarningPanel } from "@/components/workspace/early-warning-panel";
import { ResearchNotice } from "@/components/workspace/early-warning-views";
import { useApi } from "@/hooks/use-api";
import { listAreas } from "@/services/areas";
import type { Head } from "@/types/prediction";

/** Standalone page used by /dashboard/predictions (both heads) and /dashboard/risk-map (susceptibility). */
export function EarlyWarningPage({ title, heads }: { title: string; heads: Head[] }) {
  const areas = useApi((s) => listAreas(s));
  const [sel, setSel] = useState("");
  const items = areas.data?.items ?? [];
  const area = items.find((a) => a.id === sel) ?? items[0];
  return (
    <div className="space-y-4">
      <div><h1 className="text-xl font-semibold">{title}</h1><ResearchNotice /></div>
      {areas.isLoading && !areas.data ? <LoadingState label="Loading monitored areas" /> :
        areas.error ? <ErrorState title="Could not load monitored areas" message={areas.error.message} onRetry={areas.refetch} /> :
        !area ? <EmptyState icon={MapPinned} title="No monitored areas" description="Create an area first."
          action={<Link className="text-sm text-accent underline" href="/dashboard/workspace">Open the workspace</Link>} /> : (
          <>
            <label className="flex items-center gap-2 text-sm">Area
              <select value={area.id} onChange={(e) => setSel(e.target.value)} className="h-8 rounded border border-line bg-surface-2 px-2">
                {items.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select></label>
            <div className="grid gap-4 lg:grid-cols-2">{heads.map((h) => <EarlyWarningPanel key={`${area.id}-${h}`} areaId={area.id} head={h} />)}</div>
          </>
        )}
    </div>
  );
}
