export interface SessionErrorPresentation {
  action:
    | { kind: "link"; href: string; label: string }
    | { kind: "retry" }
    | { kind: "none" };
  message: string;
  title: string;
}

interface ErrorStateProps {
  onRetry: () => void;
  presentation: SessionErrorPresentation;
}

export function ShellLoading() {
  return (
    <div className="shell-gate">
      <header className="shell-gate__header">Polyglot</header>
      <main className="shell-gate__content">
        <div
          aria-label="Chargement de Polyglot"
          className="shell-loading"
          role="status"
        >
          <span className="shell-loading__indicator" aria-hidden="true" />
          <span>Chargement de votre espace...</span>
        </div>
      </main>
    </div>
  );
}

export function SessionErrorState({ onRetry, presentation }: ErrorStateProps) {
  return (
    <div className="shell-gate">
      <header className="shell-gate__header">Polyglot</header>
      <main className="shell-gate__content">
        <section className="state-message state-message--error" role="alert">
          <h1>{presentation.title}</h1>
          <p>{presentation.message}</p>
          {presentation.action.kind === "retry" ? (
            <button type="button" onClick={onRetry}>
              Réessayer
            </button>
          ) : null}
          {presentation.action.kind === "link" ? (
            <a className="button-link" href={presentation.action.href}>
              {presentation.action.label}
            </a>
          ) : null}
        </section>
      </main>
    </div>
  );
}

export function EmptyState() {
  return (
    <section className="state-message state-message--empty">
      <h2>Aucun contenu disponible</h2>
      <p>Cette destination est prête à recevoir son contenu.</p>
    </section>
  );
}
