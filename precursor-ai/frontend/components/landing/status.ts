/**
 * Honest capability status, mirroring docs/project/PROJECT_STATUS.md.
 * Nothing here is "operational": no real-data validation has been performed.
 */
export type StatusKey = "implemented-mock" | "implemented-synthetic" | "partial" | "planned";

export interface StatusInfo {
  label: string;
  /** Tailwind text/border classes (all AA on the surface colour). */
  tone: string;
}

export const STATUS: Record<StatusKey, StatusInfo> = {
  "implemented-synthetic": { label: "Implemented, synthetic-tested", tone: "text-ok border-ok/50" },
  "implemented-mock": { label: "Implemented, mock-tested", tone: "text-warn border-warn/50" },
  partial: { label: "Partially implemented", tone: "text-warn border-warn/50" },
  planned: { label: "Planned, not started", tone: "text-ink-muted border-ink-muted/50" },
};

export function statusInfo(key: StatusKey): StatusInfo {
  return STATUS[key];
}

export interface Capability {
  id: string;
  title: string;
  status: StatusKey;
  body: string;
}

export const CAPABILITIES: Capability[] = [
  {
    id: "acquisition",
    title: "Satellite data acquisition",
    status: "implemented-mock",
    body: "Catalog search and managed downloads for NISAR, Sentinel-1, NASADEM, IMERG, SMAP and the NASA Global Landslide Catalog. Anonymous catalog search was verified live; no real file has been downloaded yet.",
  },
  {
    id: "insar",
    title: "SAR / InSAR processing",
    status: "implemented-synthetic",
    body: "Displacement, coherence and mean line-of-sight velocity from NISAR products. Verified on synthetic files only; real-data validation has not been performed. No phase unwrapping or Sentinel-1 processing yet.",
  },
  {
    id: "environmental",
    title: "Environmental data integration",
    status: "implemented-synthetic",
    body: "Terrain, rainfall, soil, land cover and seismic events, clipped to an area of interest. Verified on synthetic data; soil and land cover currently give statistics only.",
  },
  {
    id: "features",
    title: "Feature extraction and time-series analysis",
    status: "partial",
    body: "Slope and aspect are computed from elevation. Further terrain features and time-series analysis are not started.",
  },
  {
    id: "prediction",
    title: "Early-prediction engine",
    status: "planned",
    body: "A research goal. No machine-learning model is implemented, and the platform produces no risk score or prediction.",
  },
  {
    id: "explainability",
    title: "Uncertainty and explainability",
    status: "planned",
    body: "Planned alongside any future model. Nothing is implemented yet.",
  },
  {
    id: "dashboard",
    title: "Interactive geospatial dashboard",
    status: "partial",
    body: "Area, data, InSAR and environmental views exist and are tested with synthetic data. The risk map and predictions pages are placeholders.",
  },
];
