import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Component, type ErrorInfo, type ReactNode } from "react";

interface AppProvidersProps {
  children: ReactNode;
  queryClient: QueryClient;
  reloadApplication?: () => void;
}

interface AppErrorBoundaryProps {
  children: ReactNode;
  onReload: () => void;
}

interface AppErrorBoundaryState {
  error: Error | null;
}

class AppErrorBoundary extends Component<
  AppErrorBoundaryProps,
  AppErrorBoundaryState
> {
  public override state: AppErrorBoundaryState = { error: null };

  public static getDerivedStateFromError(error: Error): AppErrorBoundaryState {
    return { error };
  }

  public override componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error("Uncaught application error", error, errorInfo);
  }

  public override render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="shell-gate">
          <header className="shell-gate__header">Polyglot</header>
          <main className="shell-gate__content">
            <section className="state-message state-message--error" role="alert">
              <h1>Une erreur inattendue est survenue</h1>
              <p>L'application ne peut pas continuer dans son état actuel.</p>
              <button
                type="button"
                onClick={() => {
                  this.props.onReload();
                }}
              >
                Recharger l'application
              </button>
            </section>
          </main>
        </div>
      );
    }

    return this.props.children;
  }
}

export function AppProviders({
  children,
  queryClient,
  reloadApplication = () => {
    globalThis.location.reload();
  },
}: AppProvidersProps) {
  return (
    <AppErrorBoundary onReload={reloadApplication}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </AppErrorBoundary>
  );
}
