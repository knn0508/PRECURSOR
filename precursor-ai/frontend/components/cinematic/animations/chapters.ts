export interface Chapter {
  id: string;
  kicker: string;
  title: string;
  subtitle: string;
  /** Scroll-progress window [start, end] of the master timeline. */
  range: [number, number];
  align: "center" | "left";
}

export const CHAPTERS: Chapter[] = [
  {
    id: "earth",
    kicker: "01 / Earth",
    title: "PRECURSOR AI",
    subtitle:
      "Monitoring ground-surface change with satellite SAR/InSAR and environmental data, to support future landslide early prediction.",
    range: [0, 0.15],
    align: "center",
  },
  {
    id: "observe",
    kicker: "02 / Observation",
    title: "Observe the invisible",
    subtitle: "Satellite radar reveals what conventional observation cannot.",
    range: [0.15, 0.35],
    align: "left",
  },
  {
    id: "detect",
    kicker: "03 / SAR + InSAR",
    title: "Detect surface deformation",
    subtitle: "Turning radar observations into measurable ground movement.",
    range: [0.35, 0.55],
    align: "left",
  },
  {
    id: "forecast",
    kicker: "04 / Prediction",
    title: "Toward early prediction",
    subtitle: "A research goal: combining deformation and environmental data. No machine-learning model is implemented yet.",
    range: [0.55, 0.8],
    align: "left",
  },
  {
    id: "reveal",
    kicker: "05 / Platform",
    title: "PRECURSOR AI",
    subtitle: "A research prototype working toward landslide early prediction.",
    range: [0.8, 1],
    align: "center",
  },
];
