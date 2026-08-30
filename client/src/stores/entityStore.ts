import { create } from 'zustand';
import type { SelectedEntity } from '../types/entities';

// App-level entity drawer selection. Pages call open(); the drawer is rendered
// once in AppShell so it works across route changes.

interface EntityState {
  entity: SelectedEntity | null;
  open: (entity: SelectedEntity) => void;
  close: () => void;
}

export const useEntityStore = create<EntityState>((set) => ({
  entity: null,
  open: (entity) => set({ entity }),
  close: () => set({ entity: null }),
}));
