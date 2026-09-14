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
  { to: "/admin", key: "nav.admin", icon: "users", admin: true },
  { to: "/settings", key: "nav.settings", icon: "gear" },
] as const;

export function AppShell() {
  const { me } = useAuth();
  const { t } = useLocale();
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);
  return (
    <div className="shell">
      {open ? (
        <button type="button" className="side-overlay" aria-label={t("nav.closeMenu")}
          onClick={close} />
      ) : null}
      <aside className={`sidebar${open ? " open" : ""}`} aria-label={t("nav.primaryNav")}>
        <Link to="/" className="side-brand" aria-label="Foap Creative Intelligence Dashboard" onClick={close}>
          <img src="/foap-logo.png" alt="Foap" />
        </Link>
        <nav className="side-nav">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={"end" in n && n.end}
              className={({ isActive }) => (isActive ? "active" : "")}
              onClick={close}>
              <Icon name={n.icon} size={19} />
              {t(n.key)}
            </NavLink>
          ))}
          <div className="side-gap" />
          {NAV_ACCOUNT.filter((n) => !("admin" in n && n.admin) || me?.is_admin).map((n) => (
            <NavLink key={n.to} to={n.to}
              className={({ isActive }) => (isActive ? "active" : "")}
              onClick={close}>
              <Icon name={n.icon} size={19} />
              {t(n.key)}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="maincol">
        <header className="topbar">
          <div className="topbar-inner">
            <button type="button" className="icon-btn hamburger"
              aria-label={t("nav.openMenu")} onClick={() => setOpen(true)}>
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
