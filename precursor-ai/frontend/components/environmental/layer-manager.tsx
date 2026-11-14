"use client";

import { Layers } from "lucide-react";
import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import type { FeatureCollection } from "geojson";
import { EmptyState } from "@/components/dashboard/empty-state";
import { ErrorState } from "@/components/dashboard/error-state";
import { LoadingState } from "@/components/dashboard/loading-state";
import { Notice } from "@/components/data/badges";
import type { MapRaster, MapVector } from "@/components/environmental/layer-map";
import { OriginBadge, OriginBanner, ToneBadge, layerStatusTone } from "@/components/environmental/shared";
import { Card, CardContent } from "@/components/ui/card";
import { useApi } from "@/hooks/use-api";
import {
  GRADIENT_STOPS, INSAR_LAYER_NOTE, eventFeatures, footprintCorners, isDrawableRaster, isInsarLayer, isVectorLayer,
  layerDisplayName, layerKind, layerTypeLabel, legendClasses, legendGradient,
} from "@/lib/environmental-helpers";
import { getLandslides, getLayers, getLegend, getSeismic, layerPreviewUrl } from "@/services/environmental";
import type { MonitoredArea } from "@/types/api";
import type { EventFeature, LayerRead } from "@/types/environmental";

// MapLibre needs the browser (WebGL); skip SSR.
const LayerMap = dynamic(() => import("@/components/environmental/layer-map").then((m) => m.LayerMap), {
  ssr: false,
  loading: () => <LoadingState label="Loading map" className="p-5" />,
});

const VECTOR_COLOR: Record<string, string> = { HISTORICAL_LANDSLIDES: "#f97316", SEISMIC: "#e879f9" };
const fc = (f: EventFeature[]): FeatureCollection => ({ type: "FeatureCollection", features: f as unknown as FeatureCollection["features"] });
const period = (l: LayerRead) => (l.temporal_start ? `${l.temporal_start.slice(0, 10)} to ${l.temporal_end?.slice(0, 10) ?? "?"}` : "not time-bound / unknown");

function Legend({ layer }: { layer: LayerRead }) {
  const lg = useApi((s) => getLegend(layer.id, s));
  if (lg.isLoading && !lg.data) return <LoadingState label="Loading legend" />;
  if (lg.error || !lg.data) return <p className="text-xs text-ink-muted">Legend unavailable.</p>;
  const d = lg.data;
  const g = d.kind === "continuous" ? legendGradient(d.vmin, d.vmax, d.units, d.colors) : null;
  return (
    <div className="space-y-1 text-xs" aria-label={`Legend for ${layerTypeLabel(layer.layer_type)}`}>
      {d.kind === "continuous" && (g ? (
        <div>
          <div className="h-3 w-full rounded" style={{ background: g.css }} aria-hidden />
          <div className="flex justify-between text-ink-muted"><span>{g.minLabel}</span><span>{g.maxLabel}</span></div>
          <span className="sr-only">Gradient from {g.minLabel} to {g.maxLabel}; stops {GRADIENT_STOPS.length}</span>
        </div>
      ) : <p className="text-ink-muted">Value range unknown.</p>)}
      {d.kind === "categorical" && (
        <ul className="grid grid-cols-2 gap-x-3 gap-y-0.5">
          {legendClasses(d.classes).map((c) => (
            <li key={c.key} className="flex items-center gap-1.5">
              <span className="inline-block h-3 w-3 rounded-sm border border-line" style={{ background: c.color }} aria-hidden />{c.name}
            </li>
          ))}
        </ul>
      )}
      {d.kind === "circular" && (
        <p className="text-ink-muted">Circular scale, 0-360 degrees clockwise from north (N=0, E=90, S=180, W=270): the downslope direction. Flat areas have no aspect.</p>
      )}
      {d.units && <p className="text-ink-muted">Units: {d.units}</p>}
      {d.note && <p className="text-ink-muted">{d.note}</p>}
    </div>
  );
}

interface LayerState { on: boolean; opacity: number }

function LayerCard({ layer, st, set }: { layer: LayerRead; st: LayerState; set: (s: LayerState) => void }) {
  const vector = isVectorLayer(layer.layer_type);
  const drawable = vector ? !(layer.status === "NOT_AVAILABLE" || layer.status === "FAILED") : isDrawableRaster(layer);
  const id = `lyr-${layer.id}`;
  return (
    <Card><CardContent className="space-y-2 p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <input id={id} type="checkbox" checked={st.on} disabled={!drawable} onChange={(e) => set({ ...st, on: e.target.checked })} />
        <label htmlFor={id} className="font-medium">{layerDisplayName(layer)}</label>
        <OriginBadge origin={layer.data_origin} />
        <ToneBadge tone={layerStatusTone(layer.status)}>{layer.status.replaceAll("_", " ")}</ToneBadge>
      </div>
      <OriginBanner origin={layer.data_origin} />
      {isInsarLayer(layer.layer_type) && <p className="text-xs font-semibold text-warn">{INSAR_LAYER_NOTE}</p>}
      {!drawable && <p className="text-xs text-ink-muted">{layerKind(layer.layer_type) === "raster"
        ? "No data to draw for this layer (shown as no data, not as zero)."
        : "Non-raster dataset (series or vector): listed with its status, not drawn as a map raster."}</p>}
      {drawable && st.on && (
        <>
          <label className="flex items-center gap-2 text-xs">Opacity
            <input type="range" min={0.1} max={1} step={0.05} value={st.opacity} aria-label={`${layerTypeLabel(layer.layer_type)} opacity`}
              onChange={(e) => set({ ...st, opacity: Number(e.target.value) })} />
            {Math.round(st.opacity * 100)}%</label>
          {!isVectorLayer(layer.layer_type) && <Legend layer={layer} />}
        </>
      )}
      <p className="text-xs text-ink-muted">
        Source: {layer.source_provider} / {layer.dataset_name}{layer.dataset_version ? ` ${layer.dataset_version}` : ""} · Period: {period(layer)}
      </p>
      <p className="text-xs text-ink-muted">
        Provenance: {layer.measurement_kind.replaceAll("_", " ").toLowerCase()} · validation {layer.validation_status.replaceAll("_", " ").toLowerCase()}
        {layer.label ? ` · ${layer.label}` : ""}
      </p>
    </CardContent></Card>
  );
}

export function LayerManager({ area }: { area: MonitoredArea }) {
  const layers = useApi((s) => getLayers(area.id, s));
  const ls = useApi((s) => getLandslides(area.id, s).catch(() => null));
  const eq = useApi((s) => getSeismic(area.id, s).catch(() => null));
  const [state, setState] = useState<Record<string, LayerState>>({});
  const get = (id: string): LayerState => state[id] ?? { on: false, opacity: 0.8 };

  const items = layers.data?.items ?? [];
  const { rasters, vectors } = useMemo(() => {
    const rs: MapRaster[] = [], vs: MapVector[] = [];
    for (const l of items) {
      const st = state[l.id] ?? { on: false, opacity: 0.8 };
      if (!st.on) continue;
      if (isVectorLayer(l.layer_type)) {
        if (l.status === "NOT_AVAILABLE" || l.status === "FAILED") continue;
        const feats = eventFeatures((l.layer_type === "SEISMIC" ? eq.data : ls.data)?.geojson);
        vs.push({ id: l.id, color: VECTOR_COLOR[l.layer_type], data: fc(feats), opacity: st.opacity });
      } else if (isDrawableRaster(l)) {
        rs.push({ id: l.id, url: layerPreviewUrl(l.id), corners: footprintCorners(l.footprint)!, opacity: st.opacity });
      }
    }
    return { rasters: rs, vectors: vs };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, state, ls.data, eq.data]);

  if (layers.isLoading && !layers.data) return <LoadingState label="Loading layers" />;
  if (layers.error) return <ErrorState title="Could not load layers" message={layers.error.message} onRetry={layers.refetch} />;

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
      <div className="space-y-2">
        <div className="relative h-[28rem] overflow-hidden rounded-lg border border-line">
          <LayerMap aoi={area.geometry} rasters={rasters} vectors={vectors} />
        </div>
        <p className="text-xs text-ink-muted">Blue outline: area of interest. No basemap is loaded. Layers are measurements or summaries of source data, not risk.</p>
      </div>
      <div className="space-y-2">
        {items.length === 0 ? (
          <EmptyState icon={Layers} title="No layers yet" description="No environmental layers exist for this area. Process it from the Overview tab; nothing is drawn until real or labelled data exists." />
        ) : (
          <>
            <Notice>Toggle a layer to draw it. Synthetic or unverified layers are always flagged.</Notice>
            {items.map((l) => <LayerCard key={l.id} layer={l} st={get(l.id)} set={(s) => setState((p) => ({ ...p, [l.id]: s }))} />)}
          </>
        )}
      </div>
    </div>
  );
}
