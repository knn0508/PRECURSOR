"use client";

import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { FeatureCollection, Geometry } from "geojson";
import { useEffect, useRef } from "react";
import type { MonitoredArea } from "@/types/api";

// Offline-safe style: plain dark background, no external tile server.
// A basemap and real data layers are added in later phases.
maplibregl.setWorkerUrl("/vendor/maplibre-gl-worker.js");

const BASE_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: "background", type: "background", paint: { "background-color": "#0a1018" } }],
};

function collectCoords(geom: Record<string, unknown>): [number, number][] {
  const out: [number, number][] = [];
  const walk = (c: unknown) => {
    if (Array.isArray(c) && typeof c[0] === "number") out.push([c[0] as number, c[1] as number]);
    else if (Array.isArray(c)) c.forEach(walk);
  };
  walk(geom.coordinates);
  return out;
}

export function AreaMap({ areas }: { areas: MonitoredArea[] }) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!container.current) return;
    const map = new maplibregl.Map({
      container: container.current,
      style: BASE_STYLE,
      center: [0, 20],
      zoom: 1,
      attributionControl: false,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      const data: FeatureCollection = {
        type: "FeatureCollection",
        features: areas.map((a) => ({
          type: "Feature",
          properties: { name: a.name },
          geometry: a.geometry as unknown as Geometry,
        })),
      };
      const src = map.getSource("areas") as maplibregl.GeoJSONSource | undefined;
      if (src) src.setData(data);
      else {
        map.addSource("areas", { type: "geojson", data });
        map.addLayer({ id: "areas-fill", type: "fill", source: "areas", paint: { "fill-color": "#38bdf8", "fill-opacity": 0.2 } });
        map.addLayer({ id: "areas-line", type: "line", source: "areas", paint: { "line-color": "#38bdf8", "line-width": 1.5 } });
      }
      const coords = areas.flatMap((a) => collectCoords(a.geometry));
      if (coords.length) {
        const b = new maplibregl.LngLatBounds(coords[0], coords[0]);
        coords.forEach((c) => b.extend(c));
        map.fitBounds(b, { padding: 40, maxZoom: 12, duration: 0 });
      }
    };
    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
  }, [areas]);

  return <div ref={container} className="h-full w-full" role="img" aria-label="Map of monitored areas" />;
}
