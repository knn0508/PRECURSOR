"use client";

import { useApi } from "@/hooks/use-api";
import { listAreas } from "@/services/areas";

export const inputCls =
  "w-full rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm text-ink placeholder:text-ink-muted";

export interface AoiState {
  areaId: string;
  geojson: string;
  start: string;
  end: string;
}
export const EMPTY_AOI: AoiState = { areaId: "", geojson: "", start: "", end: "" };

/** AOI (area dropdown OR pasted GeoJSON) + date range. `idp` keeps element ids unique per form. */
export function AoiFields({ idp, value, onChange }: { idp: string; value: AoiState; onChange: (v: AoiState) => void }) {
  const { data: areas, error } = useApi(listAreas);
  const set = (patch: Partial<AoiState>) => onChange({ ...value, ...patch });
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="space-y-1.5">
        <label htmlFor={`${idp}-area`} className="text-sm font-medium">Monitored area</label>
        <select id={`${idp}-area`} className={inputCls} value={value.areaId} onChange={(e) => set({ areaId: e.target.value })}>
          <option value="">None (paste GeoJSON instead)</option>
          {areas?.items.map((a) => (
            <option key={a.id} value={a.id}>{a.name}</option>
          ))}
        </select>
        {error && <p className="text-xs text-warn">Could not load monitored areas ({error.message}); you can still paste GeoJSON.</p>}
        {areas && areas.items.length === 0 && <p className="text-xs text-ink-muted">No monitored areas registered.</p>}
      </div>
      <div className="space-y-1.5">
        <label htmlFor={`${idp}-geojson`} className="text-sm font-medium">GeoJSON Polygon / MultiPolygon (EPSG:4326)</label>
        <textarea
          id={`${idp}-geojson`}
          rows={3}
          className={`${inputCls} font-mono text-xs`}
          placeholder='{"type":"Polygon","coordinates":[[[lon,lat],...]]}'
          value={value.geojson}
          onChange={(e) => set({ geojson: e.target.value })}
        />
        <p className="text-xs text-ink-muted">Use exactly one: an area or pasted GeoJSON.</p>
      </div>
      <div className="space-y-1.5">
        <label htmlFor={`${idp}-start`} className="text-sm font-medium">Start date</label>
        <input id={`${idp}-start`} type="date" className={inputCls} value={value.start} onChange={(e) => set({ start: e.target.value })} />
      </div>
      <div className="space-y-1.5">
        <label htmlFor={`${idp}-end`} className="text-sm font-medium">End date</label>
        <input id={`${idp}-end`} type="date" className={inputCls} value={value.end} onChange={(e) => set({ end: e.target.value })} />
      </div>
    </div>
  );
}
