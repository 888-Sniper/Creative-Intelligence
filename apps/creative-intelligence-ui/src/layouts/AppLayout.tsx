import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";
import { AccountMenu } from "@/auth/AccountMenu";
import { useTheme } from "@/app/useTheme";
import { FilterProvider } from "@/state/FilterContext";
import { FilterBar } from "@/components/FilterBar";
import { AskBar } from "@/components/AskBar";

const TABS = [
  { to: "/", label: "Overview", end: true },
  { to: "/campaigns", label: "Campaigns", end: false },
  { to: "/creatives", label: "Creatives", end: false },
  { to: "/compare", label: "Compare", end: false },
  { to: "/analyst", label: "Analyst", end: false },
  { to: "/benchmarks", label: "Benchmarks", end: false },
  { to: "/reports", label: "Reports", end: false },
  { to: "/profile", label: "Profile", end: false },
  { to: "/settings", label: "Settings", end: false },
] as const;

/** Application shell: Foap branding, primary nav, theme toggle. View ports
 *  render inside <Outlet />. Admin tab is admin-only (presentation layer;
 *  every admin API re-authorizes server-side). */
export function AppLayout() {
  const { me } = useAuth();
  const { toggle } = useTheme();
  const tabClass = ({ isActive }: { isActive: boolean }) =>
    isActive ? "tab tab-active" : "tab";
  return (
    <>
      <header className="app-header">
        <div className="app-header-inner">
          <NavLink to="/" className="brand" aria-label="Foap Creative Intelligence Home">
            <img src="/foap-logo.png" alt="Foap" onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
          </NavLink>
          <nav className="main-nav" aria-label="Primary">
            {TABS.map((t) => (
              <NavLink key={t.to} to={t.to} end={t.end} className={tabClass}>
                {t.label}
              </NavLink>
            ))}
            {me?.is_admin ? (
              <NavLink to="/admin" className={tabClass}>
                Admin
              </NavLink>
            ) : null}
          </nav>
          <span className="header-spacer"></span>
          <button type="button" className="theme-btn" aria-label="Toggle Light And Dark Mode" onClick={toggle}>
            Light/Dark
          </button>
        </div>
      </header>
      <div className="container">
        <FilterProvider>
          <FilterBar />
          <AskBar />
          <main>
            <Outlet />
          </main>
        </FilterProvider>
      </div>
      <AccountMenu />
    </>
  );
}
