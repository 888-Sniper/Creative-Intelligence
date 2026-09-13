import { useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";
import { AccountMenu } from "@/auth/AccountMenu";
import { Icon } from "@/components/icons";
import { GlobalSearch } from "@/components/GlobalSearch";

const NAV = [
  { to: "/", label: "Dashboard", icon: "dashboard", end: true },
  { to: "/campaigns", label: "Campaigns", icon: "campaign" },
  { to: "/creatives", label: "Creatives", icon: "creatives" },
  { to: "/compare", label: "Compare", icon: "compare" },
  { to: "/benchmarks", label: "Benchmarks Library", icon: "book" },
  { to: "/insights", label: "Saved Insights", icon: "bookmark" },
  { to: "/reports", label: "Generated Reports", icon: "report" },
  { to: "/workbook", label: "Blank Workbook", icon: "workbook" },
  { to: "/ask", label: "Ask The Data", icon: "chat" },
  { to: "/analyst", label: "AI Analyst", icon: "spark" },
] as const;

const NAV_ACCOUNT = [
  { to: "/admin", label: "Admin", icon: "users", admin: true },
  { to: "/profile", label: "Profile", icon: "user" },
  { to: "/settings", label: "Settings", icon: "gear" },
] as const;

export function AppShell() {
  const { me } = useAuth();
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);
  return (
    <div className="shell">
      {open ? (
        <button type="button" className="side-overlay" aria-label="Close Menu"
          onClick={close} />
      ) : null}
      <aside className={`sidebar${open ? " open" : ""}`} aria-label="Primary">
        <Link to="/" className="side-brand" aria-label="Foap Creative Intelligence Dashboard" onClick={close}>
          <img src="/foap-logo.png" alt="Foap" />
        </Link>
        <nav className="side-nav">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={"end" in n && n.end}
              className={({ isActive }) => (isActive ? "active" : "")}
              onClick={close}>
              <Icon name={n.icon} size={19} />
              {n.label}
            </NavLink>
          ))}
          <div className="side-gap" />
          {NAV_ACCOUNT.filter((n) => !("admin" in n && n.admin) || me?.is_admin).map((n) => (
            <NavLink key={n.to} to={n.to}
              className={({ isActive }) => (isActive ? "active" : "")}
              onClick={close}>
              <Icon name={n.icon} size={19} />
              {n.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="maincol">
        <header className="topbar">
          <div className="topbar-inner">
            <button type="button" className="icon-btn hamburger"
              aria-label="Open Menu" onClick={() => setOpen(true)}>
              <Icon name="menu" size={20} />
            </button>
            <GlobalSearch />
            <Link to="/insights" className="icon-btn" aria-label="Recent Activity">
              <Icon name="bell" size={20} />
              <span className="dot" aria-hidden="true" />
            </Link>
            <AccountMenu />
          </div>
        </header>
        <main className="page">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
