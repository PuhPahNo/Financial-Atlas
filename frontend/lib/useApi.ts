"use client";

import { useEffect, useState } from "react";
import { Envelope, ApiError } from "./api";

export interface AsyncState<T> {
  data: T | null;
  meta: Envelope<T>["meta"] | null;
  loading: boolean;
  error: string | null;
}

// Generic loader for an API envelope, re-run when `deps` change.
export function useApi<T>(loader: () => Promise<Envelope<T>>, deps: unknown[]): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ data: null, meta: null, loading: true, error: null });

  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    loader()
      .then((res) => {
        if (!cancelled) setState({ data: res.data, meta: res.meta, loading: false, error: null });
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          const msg = e instanceof ApiError ? e.message : "Something went wrong.";
          setState({ data: null, meta: null, loading: false, error: msg });
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
