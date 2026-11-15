// Source badges (Phase 9). Every layer/panel carries exactly one. MODEL_PREDICTION is reserved for output of a registered real model;
// nothing in the app produces it today. PLACEHOLDER marks planned or mock content. No badge implies scientific validation.
export type SourceKind = "REAL_SATELLITE" | "REAL_DERIVED" | "SYNTHETIC_DEMO" | "STATISTICAL" | "MODEL_PREDICTION" | "PLACEHOLDER";

export const SOURCE_META: Record<SourceKind, { label: string; description: string }> = {
  REAL_SATELLITE: { label: "Real satellite", description: "Product as delivered by the provider; not scientifically validated here." },
  REAL_DERIVED: { label: "Real derived", description: "Computed here from real source data (or unverified local files); not scientifically validated." },
  SYNTHETIC_DEMO: { label: "Synthetic demo", description: "SYNTHETIC TEST DATA: not a real measurement." },
  STATISTICAL: { label: "Statistical", description: "Descriptive statistic of observed values; not a forecast and not risk." },
  MODEL_PREDICTION: { label: "Model prediction", description: "Output of a registered, real model (none exists yet)." },
  PLACEHOLDER: { label: "Placeholder", description: "Placeholder: planned or demonstration content, not data." },
};

interface LayerLike { data_origin?: string | null; measurement_kind?: string | null; layer_type?: string | null }

/** Badge for an environmental/InSAR layer. Synthetic always wins; unverified local files are never called satellite data. */
export function sourceKindForLayer(l: LayerLike): SourceKind {
  if (l.data_origin === "SYNTHETIC_FIXTURE") return "SYNTHETIC_DEMO";
  if (l.data_origin === "LOCAL_UNVERIFIED") return "REAL_DERIVED";
  if (l.data_origin === "REAL_SATELLITE") {
    const k = (l.measurement_kind ?? "").toUpperCase();
    return k.includes("DERIVED") || k.includes("NEWLY") ? "REAL_DERIVED" : "REAL_SATELLITE";
  }
  return "PLACEHOLDER";
}

/** Badge for a stored time series or indicator panel. */
export const sourceKindForSeries = (syntheticFlag: boolean): SourceKind => (syntheticFlag ? "SYNTHETIC_DEMO" : "STATISTICAL");

export const isSyntheticOrMock = (k: SourceKind) => k === "SYNTHETIC_DEMO" || k === "PLACEHOLDER";
