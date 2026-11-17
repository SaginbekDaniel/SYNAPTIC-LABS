import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import type { Dataset } from "../lib/types";
import { useApi, type ApiState } from "../lib/useApi";

const STORAGE_KEY = "nexora.activeDataset";

function readStored(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStored(id: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* storage unavailable (private mode): selection simply isn't remembered */
  }
}

interface DatasetContextValue {
  list: ApiState<{ items: Dataset[]; total: number }>;
  active: Dataset | null;
  activeId: string | null;
  setActiveId: (id: string) => void;
  refresh: () => void;
}

const Ctx = createContext<DatasetContextValue | null>(null);

export function DatasetProvider({ children }: { children: ReactNode }) {
  const [activeId, setActive] = useState<string | null>(readStored);
  const list = useApi("datasets", (signal) => api.get<{ items: Dataset[]; total: number }>("/api/v1/datasets", { limit: 50 }, signal));

  const setActiveId = useCallback((id: string) => {
    setActive(id);
    writeStored(id);
  }, []);

  // Fall back to the newest dataset if the remembered one no longer exists.
  useEffect(() => {
    const items = list.data?.items;
    if (!items) return;
    if (items.length === 0) return;
    if (!activeId || !items.some((d) => d.id === activeId)) setActiveId(items[0]!.id);
  }, [list.data, activeId, setActiveId]);

  const active = useMemo(() => list.data?.items.find((d) => d.id === activeId) ?? null, [list.data, activeId]);
  const value = useMemo(
    () => ({ list, active, activeId: active?.id ?? null, setActiveId, refresh: list.reload }),
    [list, active, setActiveId],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useDataset(): DatasetContextValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useDataset outside DatasetProvider");
  return v;
}
