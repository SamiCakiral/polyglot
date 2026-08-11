import {
  BarChart3,
  BookOpen,
  CalendarDays,
  CheckCircle2,
  Dumbbell,
  Languages,
  Menu,
  Settings,
  Wrench,
  UserRound,
  X,
  type LucideIcon,
} from "lucide-react";
import { type ReactNode, useEffect, useId, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { getShellRouteTitle } from "./navigation";
import { useActiveProfile } from "./profile-state";
import { useSession } from "./session-context";

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

interface TooltipNavLinkProps {
  accessibleLabel?: string;
  children: ReactNode;
  className?: string;
  label: string;
  to: string;
  tooltipClassName?: string;
}

function TooltipNavLink({
  accessibleLabel,
  children,
  className,
  label,
  to,
  tooltipClassName = "",
}: TooltipNavLinkProps) {
  const tooltipId = useId();

  return (
    <span className="tooltip-anchor">
      <NavLink
        {...(accessibleLabel ? { "aria-label": accessibleLabel } : {})}
        {...(className ? { className } : {})}
        aria-describedby={tooltipId}
        to={to}
      >
        {children}
      </NavLink>
      <span
        className={`control-tooltip ${tooltipClassName}`.trim()}
        id={tooltipId}
        role="tooltip"
      >
        {label}
      </span>
    </span>
  );
}

function PrimaryLink({ icon: Icon, label, to }: PrimaryNavigationItem) {
  return (
    <TooltipNavLink
      className="primary-nav__link"
      label={label}
      to={to}
      tooltipClassName="control-tooltip--rail"
    >
      <Icon aria-hidden="true" size={20} strokeWidth={1.8} />
      <span className="primary-nav__label">{label}</span>
    </TooltipNavLink>
  );
}

export function AppShell() {
  const session = useSession();
  const { activeProfile, packs, profiles, selectProfile } = useActiveProfile();
  const location = useLocation();
  const mainRef = useRef<HTMLElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const menuTooltipId = useId();
  const [menuOpen, setMenuOpen] = useState(false);
  const routeTitle = getShellRouteTitle(location.pathname);
  const displayNames = new Intl.DisplayNames(["fr"], { type: "language" });

  function profileLabel(targetVarietyId: string): string {
    const pack = packs.find((item) => item.target_variety_id === targetVarietyId);
    if (pack) {
      return displayNames.of(pack.target_language_tag) ?? pack.target_language_tag;
    }
    return "Autre langue";
  }

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
          <label className="language-switcher">
            <Languages aria-hidden="true" size={18} />
            <span className="sr-only">Langue active</span>
            <select
              aria-label="Langue active"
              value={activeProfile?.profile_id ?? ""}
              onChange={(event) => {
                selectProfile(event.target.value);
              }}
            >
              {profiles.length === 0 ? <option value="">Aucune langue</option> : null}
              {profiles.map((profile) => (
                <option key={profile.profile_id} value={profile.profile_id}>
                  {profileLabel(profile.target_variety_id)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <nav aria-label="Actions du compte" className="account-nav">
          <TooltipNavLink
            accessibleLabel="Profil de langue"
            label="Profil de langue"
            to="/language-profile"
            tooltipClassName="control-tooltip--below"
          >
            <UserRound aria-hidden="true" size={20} />
          </TooltipNavLink>
          <TooltipNavLink
            accessibleLabel="Préférences"
            label="Préférences"
            to="/settings"
            tooltipClassName="control-tooltip--below"
          >
            <Settings aria-hidden="true" size={20} />
          </TooltipNavLink>
        </nav>
        <span className="tooltip-anchor mobile-menu-anchor">
          <button
            ref={menuButtonRef}
            aria-controls="mobile-menu"
            aria-describedby={menuTooltipId}
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
          <span
            className="control-tooltip control-tooltip--menu"
            id={menuTooltipId}
            role="tooltip"
          >
            {menuOpen ? "Fermer le menu" : "Ouvrir le menu"}
          </span>
        </span>
      </header>

      <aside className="sidebar">
        <nav aria-label="Navigation principale" className="primary-nav">
          {primaryNavigation.map((item) => (
            <PrimaryLink key={item.to} {...item} />
          ))}
        </nav>
        {session.roles.some((role) => role === "author" || role === "reviewer" || role === "admin") ? (
          <nav aria-label="Navigation de l'Atelier" className="author-nav">
            <TooltipNavLink className="primary-nav__link" label="Atelier" to="/authoring" tooltipClassName="control-tooltip--rail">
              <Wrench aria-hidden="true" size={20} />
              <span className="primary-nav__label">Atelier</span>
            </TooltipNavLink>
          </nav>
        ) : null}
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
          {session.roles.some((role) => role === "author" || role === "reviewer" || role === "admin") ? (
            <NavLink to="/authoring" onClick={() => { setMenuOpen(false); }}>
              <Wrench aria-hidden="true" size={20} />
              Atelier
            </NavLink>
          ) : null}
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
