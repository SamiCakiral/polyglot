import { AlertCircle, ArrowRight, LoaderCircle } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

export function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  action?: ReactNode;
  description?: string;
  eyebrow?: string;
  title: string;
}) {
  return (
    <header className="page-header">
      <div>
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h1>{title}</h1>
        {description ? <p className="page-header__description">{description}</p> : null}
      </div>
      {action ? <div className="page-header__action">{action}</div> : null}
    </header>
  );
}

export function LoadingRegion({ label = "Chargement" }: { label?: string }) {
  return (
    <div className="inline-state" role="status">
      <LoaderCircle aria-hidden="true" className="spin" size={18} />
      {label}
    </div>
  );
}

export function ErrorRegion({ message }: { message: string }) {
  return (
    <div className="inline-state inline-state--error" role="alert">
      <AlertCircle aria-hidden="true" size={18} />
      {message}
    </div>
  );
}

export function NoProfile() {
  return (
    <section className="empty-panel">
      <p className="eyebrow">Première étape</p>
      <h2>Créez votre profil italien</h2>
      <p>Votre parcours, votre vocabulaire et vos preuves seront rattachés à ce profil.</p>
      <Link className="button-link" to="/language-profile">
        Commencer <ArrowRight aria-hidden="true" size={17} />
      </Link>
    </section>
  );
}

export function StatusPill({ children, tone = "neutral" }: { children: ReactNode; tone?: "good" | "neutral" | "warn" }) {
  return <span className={`status-pill status-pill--${tone}`}>{children}</span>;
}

export function Meter({ label, value }: { label: string; value: number }) {
  const bounded = Math.max(0, Math.min(1, value));
  const percentage = Math.round(bounded * 100);
  return (
    <div className="meter">
      <div className="meter__label"><span>{label}</span><strong>{percentage} %</strong></div>
      <div aria-label={`${label} ${String(percentage)} %`} aria-valuemax={100} aria-valuemin={0} aria-valuenow={percentage} className="meter__track" role="progressbar">
        <span style={{ width: `${String(bounded * 100)}%` }} />
      </div>
    </div>
  );
}
