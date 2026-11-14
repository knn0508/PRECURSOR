import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDateTime(iso: string) {
  return new Date(iso).toISOString().replace("T", " ").slice(0, 16) + " UTC";
}
