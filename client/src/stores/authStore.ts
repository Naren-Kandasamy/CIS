import { create } from 'zustand';

// Auth token + display name, mirrored to sessionStorage so a reload keeps the
// session. Keys are unchanged from the old App.tsx (ps1_auth_token / ps1_display_name)
// so lib/api.ts's sessionStorage fallback and any in-flight code keep working.

const TOKEN_KEY = 'ps1_auth_token';
const NAME_KEY = 'ps1_display_name';

interface AuthState {
  token: string | null;
  displayName: string;
  role: string;
  login: (token: string, displayName: string, role?: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: sessionStorage.getItem(TOKEN_KEY),
  displayName: sessionStorage.getItem(NAME_KEY) ?? '',
  role: sessionStorage.getItem('ps1_role') ?? '',
  login: (token, displayName, role = '') => {
    sessionStorage.setItem(TOKEN_KEY, token);
    sessionStorage.setItem(NAME_KEY, displayName);
    sessionStorage.setItem('ps1_role', role);
    set({ token, displayName, role });
  },
  logout: () => {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(NAME_KEY);
    sessionStorage.removeItem('ps1_role');
    set({ token: null, displayName: '', role: '' });
  },
}));

/** Non-reactive read for modules outside React (lib/*, loaders). */
export const getToken = () => useAuthStore.getState().token;
