"use client";

import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { FeatureCollection, Geometry } from "geojson";
import { useEffect, useRef } from "react";
import { AOI_COLOR, bboxOf } from "@/lib/environmental-helpers";

// Same style as area-map.tsx: OSM raster tiles are a progressive enhancement over a dark background (tile failure breaks nothing).
maplibregl.setWorkerUrl("/vendor/maplibre-gl-worker.js");
const BASE_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, maxzoom: 19, attribution: "© OpenStreetMap contributors" } },
  layers: [
    { id: "background", type: "background", paint: { "background-color": "#0a1018" } },
    { id: "osm", type: "raster", source: "osm", paint: { "raster-opacity": 0.9, "raster-saturation": -0.3, "raster-brightness-max": 0.85 } },
  ],
};

export interface MapRaster { id: string; url: string; corners: [[number, number], [number, number], [number, number], [number, number]]; opacity: number; smooth?: boolean }
export interface MapVector { id: string; color: string; data: FeatureCollection; opacity: number }
interface Props { aoi: Record<string, unknown>; rasters: MapRaster[]; vectors: MapVector[] }

export function LayerMap({ aoi, rasters, vectors }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const added = useRef<{ layers: string[]; sources: string[] }>({ layers: [], sources: [] });

  useEffect(() => {
    if (!container.current) return;
    const map = new maplibregl.Map({ container: container.current, style: BASE_STYLE, center: [0, 20], zoom: 1, attributionControl: false });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      added.current = { layers: [], sources: [] };
    };
  }, []);

  // Rebuild all overlays on any change (few layers); AOI outline is added last so it stays on top.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      for (const l of added.current.layers) if (map.getLayer(l)) map.removeLayer(l);
      for (const s of added.current.sources) if (map.getSource(s)) map.removeSource(s);
      const layers: string[] = [], sources: string[] = [];
      const src = (id: string, spec: maplibregl.SourceSpecification) => { map.addSource(id, spec); sources.push(id); };
      const lyr = (spec: maplibregl.LayerSpecification) => { map.addLayer(spec); layers.push(spec.id); };
      for (const r of rasters) {
        src(`r-${r.id}`, { type: "image", url: r.url, coordinates: r.corners });
        lyr({ id: `r-${r.id}`, type: "raster", source: `r-${r.id}`, paint: { "raster-opacity": r.opacity, "raster-resampling": r.smooth ? "linear" : "nearest" } });
      }
      for (const v of vectors) {
        src(`v-${v.id}`, { type: "geojson", data: v.data });
        lyr({ id: `v-${v.id}`, type: "circle", source: `v-${v.id}`, filter: ["==", ["geometry-type"], "Point"],
          paint: { "circle-radius": 5, "circle-color": v.color, "circle-opacity": v.opacity, "circle-stroke-color": "#fff", "circle-stroke-width": 1 } });
        lyr({ id: `v-${v.id}-fill`, type: "fill", source: `v-${v.id}`, filter: ["!=", ["geometry-type"], "Point"],
          paint: { "fill-color": v.color, "fill-opacity": v.opacity * 0.5 } });
      }
      src("aoi", { type: "geojson", data: { type: "Feature", properties: {}, geometry: aoi as unknown as Geometry } });
      lyr({ id: "aoi-line", type: "line", source: "aoi", paint: { "line-color": AOI_COLOR, "line-width": 2 } });
      added.current = { layers, sources };
    };
    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
  }, [aoi, rasters, vectors]);

  // Fit to the AOI only when the area changes, not on every toggle.
  useEffect(() => {
    const map = mapRef.current;
    const b = bboxOf(aoi);
    if (!map || !b) return;
    const fit = () => map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 40, maxZoom: 12, duration: 0 });
    if (map.isStyleLoaded()) fit();
    else map.once("load", fit);
  }, [aoi]);

  return <div ref={container} className="h-full w-full" role="img" aria-label="Map of environmental layers for the selected area" />;
}
