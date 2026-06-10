import { create } from "zustand";

import type { Deal } from "../api/client";

interface DealEditorState {
  deal: Deal | null;
  dirty: boolean;
  setDeal: (deal: Deal) => void;
  /** Immutable-ish update helper: mutate a draft copy of the deal. */
  update: (fn: (draft: Deal) => void) => void;
  markSaved: () => void;
}

export const useDealEditor = create<DealEditorState>((set) => ({
  deal: null,
  dirty: false,
  setDeal: (deal) => set({ deal, dirty: false }),
  update: (fn) =>
    set((s) => {
      if (!s.deal) return s;
      const draft = structuredClone(s.deal);
      fn(draft);
      return { deal: draft, dirty: true };
    }),
  markSaved: () => set({ dirty: false }),
}));
