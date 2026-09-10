import { createBrowserRouter } from "react-router-dom";
import { AppLayout } from "@/layouts/AppLayout";
import { AuthGate } from "@/auth/AuthGate";
import { OverviewPage } from "@/pages/OverviewPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { CampaignsPage } from "@/pages/CampaignsPage";
import { CreativesPage } from "@/pages/CreativesPage";
import { ComparePage } from "@/pages/ComparePage";
import { AnalystPage } from "@/pages/AnalystPage";
import { BenchmarksPage } from "@/pages/BenchmarksPage";
import { ReportsPage } from "@/pages/ReportsPage";
import { ProfilePage } from "@/profile/ProfilePage";
import { AdminEmployeesPage } from "@/admin/AdminEmployeesPage";
import { useAuth } from "@/auth/AuthProvider";
import type { ReactNode } from "react";

/** Admin routes render only for admins (presentation layer). The backend
 *  re-authorizes every admin API call; this never grants access by itself. */
function AdminOnly({ children }: { children: ReactNode }) {
  const { me } = useAuth();
  if (!me?.is_admin) return <p className="muted">Admin access required.</p>;
  return <>{children}</>;
}

export const router = createBrowserRouter([
  {
    element: (
      <AuthGate>
        <AppLayout />
      </AuthGate>
    ),
    children: [
      { index: true, element: <OverviewPage /> },
      { path: "campaigns", element: <CampaignsPage /> },
      { path: "creatives", element: <CreativesPage /> },
      { path: "compare", element: <ComparePage /> },
      { path: "analyst", element: <AnalystPage /> },
      { path: "benchmarks", element: <BenchmarksPage /> },
      { path: "reports", element: <ReportsPage /> },
      { path: "profile", element: <ProfilePage /> },
      { path: "settings", element: <SettingsPage /> },
      {
        path: "admin",
        element: (
          <AdminOnly>
            <AdminEmployeesPage />
          </AdminOnly>
        ),
      },
    ],
  },
]);
