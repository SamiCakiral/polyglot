interface ErrorStateProps {
  onRetry: () => void;
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

export function SessionErrorState({ onRetry }: ErrorStateProps) {
  return (
    <div className="shell-gate">
      <header className="shell-gate__header">Polyglot</header>
      <main className="shell-gate__content">
        <section className="state-message state-message--error" role="alert">
          <h1>Impossible de charger votre session</h1>
          <p>Vérifiez votre connexion, puis relancez le chargement.</p>
          <button type="button" onClick={onRetry}>
            Réessayer
          </button>
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
