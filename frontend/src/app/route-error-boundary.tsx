import { Home } from "lucide-react";
import { Link, isRouteErrorResponse, useRouteError } from "react-router-dom";

export function RouteErrorBoundary() {
  const routeError = useRouteError();
  const notFound = isRouteErrorResponse(routeError) && routeError.status === 404;

  return (
    <main className="route-error">
      <section className="state-message state-message--error" role="alert">
        <h1>{notFound ? "Page introuvable" : "Impossible d'afficher cette page"}</h1>
        <p>La navigation a été interrompue avant l'affichage du contenu.</p>
        <Link className="button-link" to="/today">
          <Home aria-hidden="true" size={18} />
          Revenir à aujourd'hui
        </Link>
      </section>
    </main>
  );
}
