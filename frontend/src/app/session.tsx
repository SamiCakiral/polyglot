import type { ReactNode } from "react";

import { SessionErrorState, ShellLoading } from "../components/shell-states";
import { useGetCurrentSession } from "../generated/polyglot";
import { SessionContext } from "./session-context";

interface SessionBoundaryProps {
  children: ReactNode;
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

  if (sessionQuery.isError || sessionQuery.data.status !== 200) {
    return <SessionErrorState onRetry={() => void sessionQuery.refetch()} />;
  }

  return (
    <SessionContext.Provider value={sessionQuery.data.data}>
      {children}
    </SessionContext.Provider>
  );
}
