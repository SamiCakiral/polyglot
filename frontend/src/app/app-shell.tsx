import {
  BarChart3,
  BookOpen,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  Dumbbell,
  Languages,
  Menu,
  Settings,
  UserRound,
  X,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { getShellRouteTitle } from "./navigation";

interface PrimaryNavigationItem {
  icon: LucideIcon;
  label: string;
  to: string;
}

const primaryNavigation: readonly PrimaryNavigationItem[] = [
  { to: "/today", label: "Aujourd'hui", icon: CalendarDays },
  { to: "/learn", label: "Apprendre", icon: BookOpen },
  { to: "/practice", label: "S'entraîner", icon: Dumbbell },
  { to: "/vocabulary", label: "Vocabulaire", icon: Languages },
  { to: "/progress", label: "Progression", icon: BarChart3 },
  { to: "/assess", label: "Évaluer", icon: CheckCircle2 },
] as const;

const mobileNavigation = primaryNavigation.slice(0, 5);

function PrimaryLink({ icon: Icon, label, to }: PrimaryNavigationItem) {
  return (
    <NavLink className="primary-nav__link" to={to}>
      <Icon aria-hidden="true" size={20} strokeWidth={1.8} />
      <span className="primary-nav__label">{label}</span>
    </NavLink>
  );
}

export function AppShell() {
  const location = useLocation();
  const mainRef = useRef<HTMLElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const routeTitle = getShellRouteTitle(location.pathname);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
        menuButtonRef.current?.focus();
      }
    };

    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [menuOpen]);

  return (
    <div className="app-shell">
      <a
        className="skip-link"
        href="#main-content"
        onClick={(event) => {
          event.preventDefault();
          mainRef.current?.focus();
        }}
      >
        Aller au contenu principal
      </a>

      <header className="topbar">
        <div className="topbar__brand">Polyglot</div>
        <div className="topbar__context">
          <span className="topbar__route">{routeTitle}</span>
          <NavLink
            aria-label="Langue active : Italien"
            className="language-switcher"
            to="/language-profile"
          >
            <Languages aria-hidden="true" size={18} />
            <span>Italien</span>
            <ChevronDown aria-hidden="true" size={16} />
          </NavLink>
        </div>
        <nav aria-label="Actions du compte" className="account-nav">
          <NavLink aria-label="Profil de langue" to="/language-profile">
            <UserRound aria-hidden="true" size={20} />
          </NavLink>
          <NavLink aria-label="Préférences" to="/settings">
            <Settings aria-hidden="true" size={20} />
          </NavLink>
        </nav>
        <button
          ref={menuButtonRef}
          aria-controls="mobile-menu"
          aria-expanded={menuOpen}
          aria-label={menuOpen ? "Fermer le menu" : "Ouvrir le menu"}
          className="mobile-menu-button"
          type="button"
          onClick={() => {
            setMenuOpen((open) => !open);
          }}
        >
          {menuOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
        </button>
      </header>

      <aside className="sidebar">
        <nav aria-label="Navigation principale" className="primary-nav">
          {primaryNavigation.map((item) => (
            <PrimaryLink key={item.to} {...item} />
          ))}
        </nav>
      </aside>

      {menuOpen ? (
        <nav aria-label="Menu secondaire" className="mobile-menu" id="mobile-menu">
          <NavLink
            to="/assess"
            onClick={() => {
              setMenuOpen(false);
            }}
          >
            <CheckCircle2 aria-hidden="true" size={20} />
            Évaluer
          </NavLink>
          <NavLink
            to="/language-profile"
            onClick={() => {
              setMenuOpen(false);
            }}
          >
            <UserRound aria-hidden="true" size={20} />
            Profil de langue
          </NavLink>
          <NavLink
            to="/settings"
            onClick={() => {
              setMenuOpen(false);
            }}
          >
            <Settings aria-hidden="true" size={20} />
            Préférences
          </NavLink>
        </nav>
      ) : null}

      <main ref={mainRef} className="main-content" id="main-content" tabIndex={-1}>
        <Outlet />
      </main>

      <nav aria-label="Navigation mobile" className="mobile-navigation">
        {mobileNavigation.map(({ icon: Icon, label, to }) => (
          <NavLink key={to} to={to}>
            <Icon aria-hidden="true" size={20} strokeWidth={1.8} />
            <span className="mobile-navigation__label">{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
