"use client";

import { useState } from "react";
import { inputCls } from "@/components/data/aoi-fields";
import { apiPost } from "@/lib/api-client";
import { ApiError } from "@/lib/api-client";
import { parseAoiGeoJson } from "@/lib/workspace-helpers";
import type { MonitoredArea } from "@/types/api";

/** Create a monitored area from an uploaded GeoJSON file (any region; EPSG:4326 lon/lat). The API re-validates the geometry. */
export function AoiUpload({ onCreated }: { onCreated: (a: MonitoredArea) => void }) {
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");

  const onFile = async (f: File | undefined) => {
    if (!f) return;
    const parsed = parseAoiGeoJson(await f.text());
    if (!parsed.ok) return setMsg({ ok: false, text: parsed.error });
    const nm = (name || parsed.name || f.name.replace(/\.[^.]+$/, "")).trim();
    setBusy(true);
    try {
      const a = await apiPost<MonitoredArea>("/areas", { name: nm, geometry: parsed.geometry });
      setMsg({ ok: true, text: `Created area "${a.name}".` });
      onCreated(a);
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError ? e.message : "Upload failed" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2 rounded-lg border border-line p-3 text-sm">
      <p className="font-medium">Add an area of interest</p>
      <label className="block text-xs">Name (optional)<input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} maxLength={200} /></label>
      <label className="block text-xs">GeoJSON file (Polygon or MultiPolygon, lon/lat)
        <input type="file" accept=".geojson,.json,application/geo+json,application/json" disabled={busy} onChange={(e) => void onFile(e.target.files?.[0])} className="mt-1 block text-xs" /></label>
      {msg && <p role={msg.ok ? "status" : "alert"} className={msg.ok ? "text-xs text-ink-muted" : "text-xs font-semibold text-danger"}>{msg.text}</p>}
      <p className="text-xs text-ink-muted">Drawing polygons on the map is not implemented (no drawing library is installed); use upload or an existing area.</p>
    </div>
  );
}
