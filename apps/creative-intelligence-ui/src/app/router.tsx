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

/** A07: the Analyst page partitions in-flight and stored chat state by
 *  the signed-in employee, so late responses from the previous
 *  account are dropped instead of rendered under the new identity. */
function AnalystRoute() {
  const { me } = useAuth();
  return <AnalystPage accountKey={me?.employee?.id ?? ""} />;
}

/** A07: the protected tree remounts whenever the signed-in employee
 *  changes, so no account-specific component state (Analyst
 *  conversations, filters, drafts) can survive an account switch. */
function KeyedLayout() {
  const { me } = useAuth();
  return <AppLayout key={me?.employee?.id ?? "signed-out"} />;
}

export const router = createBrowserRouter([
  {
    element: (
      <AuthGate>
        <KeyedLayout />
      </AuthGate>
    ),
    children: [
      { index: true, element: <OverviewPage /> },
      { path: "campaigns", element: <CampaignsPage /> },
      { path: "creatives", element: <CreativesPage /> },
      { path: "compare", element: <ComparePage /> },
      { path: "analyst", element: <AnalystRoute /> },
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
