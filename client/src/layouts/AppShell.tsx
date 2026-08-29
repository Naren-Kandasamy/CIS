import { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import CaseDrawerSidebar from '../components/nav/CaseDrawerSidebar';
import EntityDrawer from '../components/dashboard/EntityDrawer';
import { useAuthStore } from '../stores/authStore';
import { useEntityStore } from '../stores/entityStore';
import { warmup } from '../lib/api';

// The authed shell: paper background, folder-spine sidebar, routed content, and
// the app-level entity drawer. Also owns the pipeline warm-up heartbeat that
// used to live in App.tsx.

export default function AppShell() {
  const token = useAuthStore((s) => s.token);
  const entity = useEntityStore((s) => s.entity);
  const closeEntity = useEntityStore((s) => s.close);

  useEffect(() => {
    if (!token) return;
    warmup();
    const id = window.setInterval(warmup, 4 * 60_000);
    return () => window.clearInterval(id);
  }, [token]);

  return (
    <>
      <div className="ambient-bg" />
      <div className="app-container">
        <CaseDrawerSidebar />
        <main className="shell-main">
          <Outlet />
        </main>
      </div>
      <EntityDrawer entity={entity} onClose={closeEntity} />
    </>
  );
}
