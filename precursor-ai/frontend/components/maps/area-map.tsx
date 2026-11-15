"use client";

import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { FeatureCollection, Geometry } from "geojson";
import { useEffect, useRef } from "react";
import type { MonitoredArea } from "@/types/api";

// Offline-safe style: plain dark background, no external tile server.
// A basemap and real data layers are added in later phases.
maplibregl.setWorkerUrl("/vendor/maplibre-gl-worker.js");

// OSM raster tiles are a progressive enhancement: if they fail to load the dark background stays and nothing else breaks.
const BASE_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, maxzoom: 19, attribution: "© OpenStreetMap contributors" } },
  layers: [
    { id: "background", type: "background", paint: { "background-color": "#0a1018" } },
    { id: "osm", type: "raster", source: "osm", paint: { "raster-opacity": 0.9, "raster-saturation": -0.3, "raster-brightness-max": 0.85 } },
  ],
};

/** Research raster drawn over the basemap (e.g. the displacement forecast). `bounds` = [west, south, east, north]. */
export interface MapOverlay { imageUrl: string; bounds: [number, number, number, number]; corners: [number, number][]; label: string }

function collectCoords(geom: Record<string, unknown>): [number, number][] {
  const out: [number, number][] = [];
  const walk = (c: unknown) => {
    if (Array.isArray(c) && typeof c[0] === "number") out.push([c[0] as number, c[1] as number]);
    else if (Array.isArray(c)) c.forEach(walk);
  };
  walk(geom.coordinates);
  return out;
}

export function AreaMap({ areas, overlay }: { areas: MonitoredArea[]; overlay?: MapOverlay | null }) {
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
        map.addLayer({ id: "areas-fill", type: "fill", source: "areas", paint: { "fill-color": "#38bdf8", "fill-opacity": overlay ? 0 : 0.2 } });
        map.addLayer({ id: "areas-line", type: "line", source: "areas", paint: { "line-color": "#38bdf8", "line-width": 1.5 } });
      }
      map.setPaintProperty("areas-fill", "fill-opacity", overlay ? 0 : 0.2); // outline only over a data layer, so the area does not tint it blue
      const coords = areas.flatMap((a) => collectCoords(a.geometry));
      if (coords.length && !overlay) {
        const b = new maplibregl.LngLatBounds(coords[0], coords[0]);
        coords.forEach((c) => b.extend(c));
        map.fitBounds(b, { padding: 40, maxZoom: 12, duration: 0 });
      }
    };
    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
  }, [areas, overlay]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !overlay) return;
    const [w, s, e, n] = overlay.bounds;
    const apply = () => {
      const c = overlay.corners;
      const coords: [[number, number], [number, number], [number, number], [number, number]] = [c[0], c[1], c[2], c[3]];
      const src = map.getSource("overlay") as maplibregl.ImageSource | undefined;
      if (src) src.updateImage({ url: overlay.imageUrl, coordinates: coords });
      else {
        map.addSource("overlay", { type: "image", url: overlay.imageUrl, coordinates: coords });
        map.addLayer({ id: "overlay", type: "raster", source: "overlay", paint: { "raster-opacity": 0.72, "raster-resampling": "linear" } });

      }
      map.fitBounds([[w, s], [e, n]], { padding: 24, maxZoom: 15, duration: 0 });
    };
    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
  }, [overlay]);

  return <div ref={container} className="h-full w-full" role="img" aria-label="Map of monitored areas" />;
}
