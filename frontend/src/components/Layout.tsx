import {
  BookOpen,
  Moon,
  Sun,
  Monitor,
  WifiOff,
  PanelLeft,
  ListFilter,
  BarChart3,
  Menu,
  X,
} from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { HeaderActionsContext } from "./PageHeaderActions";

export function Layout() {
  const { pathname } = useLocation();
  const pageTitle = pathname.startsWith("/review/")
    ? "Document review"
    : ((
        {
          "/": "Batch Upload",
          "/rules": "Official rules",
          "/items": "Review by item",
          "/scorecard": "Evaluation scorecard",
          "/system": "System status",
          "/offline": "Offline status",
        } as Record<string, string>
      )[pathname] ?? "Review workspace");
  const [menuOpen, setMenuOpen] = useState(false);
  const [actionsHost, setActionsHost] = useState<HTMLDivElement | null>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  const sidebar = useRef<HTMLElement>(null);
  useEffect(() => {
    window.scrollTo({ top: 0 });
    document.getElementById("main")?.focus({ preventScroll: true });
    setMenuOpen(false);
  }, [pathname]);
  useEffect(() => {
    if (menuOpen)
      sidebar.current
        ?.querySelector<HTMLButtonElement>(".mobile-nav-close")
        ?.focus();
  }, [menuOpen]);
  function closeMenu() {
    setMenuOpen(false);
    menuButton.current?.focus();
  }
  const [dark, setDark] = useState(() => {
    const saved = localStorage.getItem("spr-theme");
    const value = saved
      ? saved === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    document.documentElement.dataset.theme = value ? "dark" : "light";
    return value;
  });
  function toggleTheme() {
    const value = !dark;
    document.documentElement.dataset.theme = value ? "dark" : "light";
    localStorage.setItem("spr-theme", value ? "dark" : "light");
    setDark(value);
  }
  return (
    <HeaderActionsContext.Provider value={actionsHost}>
      <a className="skip" href="#main">
        Skip to content
      </a>
      <button
        ref={menuButton}
        className="mobile-nav-toggle"
        aria-controls="workspace-navigation"
        aria-expanded={menuOpen}
        onClick={() => (menuOpen ? closeMenu() : setMenuOpen(true))}
      >
        <Menu size={18} /> Menu
      </button>
      {menuOpen && (
        <button
          className="nav-backdrop"
          tabIndex={-1}
          aria-hidden="true"
          aria-label="Close navigation"
          onClick={closeMenu}
        />
      )}
      <div className="workspace">
        <aside
          ref={sidebar}
          id="workspace-navigation"
          className="sidebar"
          data-open={menuOpen}
          onKeyDown={(event) => {
            if (!menuOpen || !matchMedia("(max-width: 700px)").matches) return;
            if (event.key === "Escape") {
              event.preventDefault();
              closeMenu();
            }
            if (event.key !== "Tab") return;
            const controls = Array.from(
              sidebar.current?.querySelectorAll<HTMLElement>("a,button") ?? [],
            ).filter((element) => element.offsetParent !== null);
            const first = controls[0],
              last = controls[controls.length - 1];
            if (event.shiftKey && document.activeElement === first) {
              event.preventDefault();
              last?.focus();
            }
            if (!event.shiftKey && document.activeElement === last) {
              event.preventDefault();
              first?.focus();
            }
          }}
        >
          <button
            className="mobile-nav-close"
            onClick={closeMenu}
            aria-label="Close navigation"
          >
            <X size={18} /> Close
          </button>
          <div className="brand">
            <span className="brand-icon">S</span>
            <div>
              SPR<span>REVIEW WORKSPACE</span>
            </div>
          </div>
          <nav
            aria-label="Main navigation"
            onClick={(event) => {
              if (menuOpen && (event.target as Element).closest("a"))
                closeMenu();
            }}
          >
            <NavLink to="/" end>
              <PanelLeft size={18} /> Batch Upload
            </NavLink>
            <NavLink to="/rules">
              <BookOpen size={18} /> Official rules{" "}
              <span className="nav-count">39</span>
            </NavLink>
            <NavLink to="/items">
              <ListFilter size={18} />
              Review by item
            </NavLink>
            <NavLink to="/scorecard">
              <BarChart3 size={18} />
              Evaluation scorecard
            </NavLink>
            <NavLink to="/system">
              <Monitor size={18} /> System status
            </NavLink>
            <NavLink to="/offline">
              <WifiOff size={18} /> Offline status
            </NavLink>
          </nav>
          <div className="sidebar-bottom">
            <span className="sidebar-status">
              <span className="local-dot" /> Local workspace
            </span>
            <button className="theme-toggle" onClick={toggleTheme}>
              {dark ? <Sun size={17} /> : <Moon size={17} />} Use{" "}
              {dark ? "light" : "dark"} theme
            </button>
          </div>
        </aside>
        <div className="content-wrap">
          <header className="page-topbar">
            <h1 className="topbar-title">{pageTitle}</h1>
            {pathname === "/" ? (
              <span className="auix-logo" role="img" aria-label="AUiX">
                <span aria-hidden="true">
                  AUi<span className="auix-logo-x">X</span>
                </span>
              </span>
            ) : (
              <div className="page-header-actions" ref={setActionsHost} />
            )}
          </header>
          <main id="main" tabIndex={-1}>
            <Outlet />
          </main>
        </div>
      </div>
    </HeaderActionsContext.Provider>
  );
}
