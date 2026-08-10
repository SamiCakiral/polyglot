import { EmptyState } from "../components/shell-states";

interface ShellRouteProps {
  title: string;
}

export function ShellRoute({ title }: ShellRouteProps) {
  return (
    <div className="route-view">
      <header className="route-view__header">
        <h1>{title}</h1>
      </header>
      <EmptyState />
    </div>
  );
}

export function NotFoundRoute() {
  return (
    <div className="route-view">
      <header className="route-view__header">
        <p className="route-view__eyebrow">404</p>
        <h1>Page introuvable</h1>
      </header>
      <p>La destination demandée n'existe pas.</p>
    </div>
  );
}
