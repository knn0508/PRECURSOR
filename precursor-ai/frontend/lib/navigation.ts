import {
  Activity,
  Bell,
  Database,
  HardDriveDownload,
  LayoutDashboard,
  LineChart,
  Map,
  MapPinned,
  Layers,
  Radar,
  Settings,
  Compass,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { label: "Overview", href: "/dashboard", icon: LayoutDashboard },
  { label: "Workspace", href: "/dashboard/workspace", icon: Compass },
  { label: "Susceptibility Map", href: "/dashboard/risk-map", icon: Map },
  { label: "Monitored Areas", href: "/dashboard/areas", icon: MapPinned },
  { label: "Satellite Data", href: "/dashboard/satellite-data", icon: Database },
  { label: "Data Acquisition", href: "/dashboard/data", icon: HardDriveDownload },
  { label: "Environmental", href: "/dashboard/environmental", icon: Layers },
  { label: "Deformation (InSAR)", href: "/dashboard/insar", icon: Radar },
  { label: "Displacement Forecast", href: "/dashboard/displacement", icon: TrendingUp },
  { label: "Predictions", href: "/dashboard/predictions", icon: Activity },
  { label: "Analytics", href: "/dashboard/analytics", icon: LineChart },
  { label: "Alerts", href: "/dashboard/alerts", icon: Bell },
  { label: "Settings", href: "/dashboard/settings", icon: Settings },
];
