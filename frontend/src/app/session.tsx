import type { ReactNode } from "react";

import {
  SessionErrorState,
  ShellLoading,
  type SessionErrorPresentation,
} from "../components/shell-states";
import type { ProblemResponse } from "../generated/model";
import { useGetCurrentSession } from "../generated/polyglot";
import { SessionContext } from "./session-context";

interface SessionBoundaryProps {
  children: ReactNode;
}

const transportFailure: SessionErrorPresentation = {
  title: "Connexion interrompue",
  message: "Le serveur est injoignable. Vérifiez votre connexion avant de réessayer.",
  action: { kind: "retry" },
};

function presentSessionProblem(
  status: number,
  problem: ProblemResponse,
): SessionErrorPresentation {
  if (status === 401 || problem.code === "unauthenticated") {
    return {
      title: "Votre session a expiré",
      message: "Reconnectez-vous pour ouvrir une nouvelle session sécurisée.",
      action: { kind: "link", href: "/login", label: "Se reconnecter" },
    };
  }

  if (status === 403 || problem.code === "forbidden") {
    return {
      title: "Vous n'avez pas accès à cette page",
      message: "Utilisez un compte autorisé pour accéder à cet espace.",
      action: { kind: "link", href: "/login", label: "Revenir à la connexion" },
    };
  }

  if (!problem.retryable) {
    return {
      title: "Votre session ne peut pas être ouverte",
      message: "Cette erreur ne peut pas être rejouée depuis le navigateur.",
      action: { kind: "none" },
    };
  }

  if (status === 429 || problem.code === "rate_limited") {
    return {
      title: "Trop de demandes",
      message: "Attendez avant de lancer une nouvelle tentative manuelle.",
      action: { kind: "retry" },
    };
  }

  if (status >= 500) {
    return {
      title: "Service temporairement indisponible",
      message: "Le serveur autorise une nouvelle tentative manuelle.",
      action: { kind: "retry" },
    };
  }

  return {
    title: "Impossible de charger votre session",
    message: "La requête peut être relancée sans modifier de données.",
    action: { kind: "retry" },
  };
}

export function SessionBoundary({ children }: SessionBoundaryProps) {
  const sessionQuery = useGetCurrentSession({
    query: {
      retry: false,
    },
  });

  if (sessionQuery.isPending) {
    return <ShellLoading />;
  }

  if (sessionQuery.isError) {
    return (
      <SessionErrorState
        presentation={transportFailure}
        onRetry={() => void sessionQuery.refetch()}
      />
    );
  }

  if (sessionQuery.data.status !== 200) {
    return (
      <SessionErrorState
        presentation={presentSessionProblem(
          sessionQuery.data.status,
          sessionQuery.data.data,
        )}
        onRetry={() => void sessionQuery.refetch()}
      />
    );
  }

  return (
    <SessionContext.Provider value={sessionQuery.data.data}>
      {children}
    </SessionContext.Provider>
  );
}
