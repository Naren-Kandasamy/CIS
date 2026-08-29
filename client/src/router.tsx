import { createBrowserRouter, Navigate } from 'react-router-dom';
import RequireAuth from './components/auth/RequireAuth';
import AppShell from './layouts/AppShell';
import LoginPage from './pages/LoginPage';
import CasesIndexPage from './pages/CasesIndexPage';
import GlobalDashboardPage from './pages/GlobalDashboardPage';
import CaseWorkspacePage from './pages/CaseWorkspacePage';
import CorkboardPage from './pages/CorkboardPage';
import SessionChatPage from './pages/SessionChatPage';
import NotFoundPage from './pages/NotFoundPage';

export const router = createBrowserRouter(
  [
    { path: '/login', element: <LoginPage /> },
    {
      element: <RequireAuth />,
      children: [
        {
          element: <AppShell />,
          children: [
            { index: true, element: <Navigate to="/cases" replace /> },
            { path: 'cases', element: <CasesIndexPage /> },
            { path: 'dashboard', element: <GlobalDashboardPage /> },
            { path: 'cases/:caseId', element: <CaseWorkspacePage /> },
            { path: 'cases/:caseId/board', element: <CorkboardPage /> },
            { path: 'cases/:caseId/sessions/:sessionId', element: <SessionChatPage /> },
            { path: '*', element: <NotFoundPage /> },
          ],
        },
      ],
    },
  ],
  { basename: '/app' },
);
