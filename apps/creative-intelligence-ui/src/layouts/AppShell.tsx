import { useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";
import { AccountMenu } from "@/auth/AccountMenu";
import { Icon } from "@/components/icons";
import { GlobalSearch } from "@/components/GlobalSearch";
import { SampleScopeBanner } from "@/components/SampleScopeBanner";
import { useLocale } from "@/i18n";

const NAV = [
  { to: "/", key: "nav.dashboard", icon: "dashboard", end: true },
  { to: "/campaigns", key: "nav.campaigns", icon: "campaign" },
  { to: "/creatives", key: "nav.creatives", icon: "creatives" },
  { to: "/compare", key: "nav.compare", icon: "compare" },
  { to: "/benchmarks", key: "nav.benchmarks", icon: "book" },
  { to: "/insights", key: "nav.insights", icon: "bookmark" },
  { to: "/reports", key: "nav.reports", icon: "report" },
  { to: "/workbook", key: "nav.workbook", icon: "workbook" },
  { to: "/ask", key: "nav.ask", icon: "chat" },
  { to: "/analyst", key: "nav.analyst", icon: "spark" },
] as const;

const NAV_ACCOUNT = [
  { to: "/providers", key: "nav.providers", icon: "spark", admin: true },
  { to: "/admin", key: "nav.admin", icon: "users", admin: true },
  { to: "/settings", key: "nav.settings", icon: "gear" },
] as const;

const COLLAPSE_KEY = "ci-shell-collapsed";

function loadCollapsed(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSE_KEY) === "1";
  } catch {
    return false;
  }
}

export function AppShell() {
  const { me } = useAuth();
  const { t } = useLocale();
  // Mobile drawer state (slide-over under 900px) — independent from
  // the desktop collapse state below.
  const [open, setOpen] = useState(false);
  // Desktop collapse state: the sidebar shrinks to an icon rail and
  // the content column reflows into the freed space (flex layout).
  // Persisted per browser so it survives refresh and navigation.
  const [collapsed, setCollapsed] = useState(loadCollapsed);
  const close = () => setOpen(false);
  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
      } catch {
        /* private mode: collapse still works for the session */
      }
      return next;
    });
  };
  const collapseLabel = collapsed ? t("nav.expandSidebar") : t("nav.collapseSidebar");
  return (
    <div className={`shell${collapsed ? " shell-collapsed" : ""}`}>
      {open ? (
        <button type="button" className="side-overlay" aria-label={t("nav.closeMenu")}
          onClick={close} />
      ) : null}
      <aside className={`sidebar${open ? " open" : ""}${collapsed ? " collapsed" : ""}`}
        aria-label={t("nav.primaryNav")}>
        <Link to="/" className="side-brand" aria-label="Foap Creative Intelligence Dashboard" onClick={close}>
          <img src="/foap-logo.png" alt="Foap" />
        </Link>
        <nav className="side-nav">
          {NAV.map((n) => {
            const label = t(n.key);
            return (
              <NavLink key={n.to} to={n.to} end={"end" in n && n.end}
                className={({ isActive }) => (isActive ? "active" : "")}
                onClick={close}
                title={collapsed ? label : undefined}
                aria-label={collapsed ? label : undefined}>
                <Icon name={n.icon} size={19} />
                <span className="lbl">{label}</span>
              </NavLink>
            );
          })}
          <div className="side-gap" />
          {NAV_ACCOUNT.filter((n) => !("admin" in n && n.admin) || me?.is_admin).map((n) => {
            const label = t(n.key);
            return (
              <NavLink key={n.to} to={n.to}
                className={({ isActive }) => (isActive ? "active" : "")}
                onClick={close}
                title={collapsed ? label : undefined}
                aria-label={collapsed ? label : undefined}>
                <Icon name={n.icon} size={19} />
                <span className="lbl">{label}</span>
              </NavLink>
            );
          })}
        </nav>
      </aside>
      <div className="maincol">
        <header className="topbar">
          <div className="topbar-inner">
            <button type="button" className="icon-btn hamburger"
              aria-label={t("nav.openMenu")} onClick={() => setOpen(true)}>
              <Icon name="menu" size={20} />
            </button>
            <button type="button" className="icon-btn collapse-btn"
              aria-label={collapseLabel} aria-expanded={!collapsed}
              title={collapseLabel} onClick={toggleCollapsed}>
              <Icon name="menu" size={20} />
            </button>
            <GlobalSearch />
            <Link to="/insights" className="icon-btn" aria-label={t("nav.recentActivity")}>
              <Icon name="bell" size={20} />
              <span className="dot" aria-hidden="true" />
            </Link>
            <AccountMenu />
          </div>
        </header>
        <main className="page">
          <SampleScopeBanner />
          <Outlet />
        </main>
      </div>
    </div>
  );
}
