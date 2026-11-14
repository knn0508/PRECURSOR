"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api-client";

export interface ApiState<T> {
  data: T | null;
  error: ApiError | null;
  isLoading: boolean;
  refetch: () => void;
}

/** Runs `fetcher` on mount and on refetch. Cancels in-flight requests on unmount. */
export function useApi<T>(fetcher: (signal: AbortSignal) => Promise<T>): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setIsLoading(true);
    fetcher(controller.signal)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e: unknown) => {
        if (controller.signal.aborted) return;
        setError(e instanceof ApiError ? e : new ApiError("Unexpected error", null, "unknown"));
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick]);

  const refetch = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, isLoading, refetch };
}
