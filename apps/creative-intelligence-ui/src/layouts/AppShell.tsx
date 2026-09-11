import { useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";
import { Icon } from "@/components/icons";

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

function initials(name: string): string {
  const bits = name.trim().split(/\s+/).filter(Boolean);
  if (!bits.length) return "•";
  return (bits[0][0] + (bits[1]?.[0] ?? "")).toUpperCase();
}

export function AppShell() {
  const { me } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const employee = me?.employee;
  const name =
    `${employee?.first_name ?? ""} ${employee?.last_name ?? ""}`.trim() ||
    employee?.email ||
    "Employee";
  const close = () => setOpen(false);
  return (
    <div className="shell">
      {open ? (
        <button type="button" className="side-overlay" aria-label="Close menu"
          onClick={close} />
      ) : null}
      <aside className={`sidebar${open ? " open" : ""}`} aria-label="Primary">
        <Link to="/" className="side-brand" onClick={close}>
          <img src="/foap-logo.png" alt="" aria-hidden="true" />
          <b>Foap</b>
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
              aria-label="Open menu" onClick={() => setOpen(true)}>
              <Icon name="menu" size={20} />
            </button>
            <form className="globalsearch" role="search"
              onSubmit={(e) => {
                e.preventDefault();
                if (query.trim()) {
                  navigate(`/campaigns?find=${encodeURIComponent(query.trim())}`);
                  setQuery("");
                }
              }}>
              <Icon name="search" size={17} />
              <input value={query} onChange={(e) => setQuery(e.target.value)}
                placeholder="Search for campaigns, creatives, or insights…"
                aria-label="Search campaigns, creatives, or insights" />
            </form>
            <Link to="/insights" className="icon-btn" aria-label="Recent activity">
              <Icon name="bell" size={20} />
              <span className="dot" aria-hidden="true" />
            </Link>
            <Link to="/profile" className="user-chip" aria-label={`${name}, profile`}>
              <span className="avatar" aria-hidden="true">{initials(name)}</span>
              <span className="uname">{name}</span>
              <Icon name="chev" size={15} />
            </Link>
          </div>
        </header>
        <main className="page">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
