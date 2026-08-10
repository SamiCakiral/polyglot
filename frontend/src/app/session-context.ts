import { createContext, useContext } from "react";

import type { CurrentSessionResponse } from "../generated/model";

export const SessionContext = createContext<CurrentSessionResponse | null>(null);

export function useSession(): CurrentSessionResponse {
  const session = useContext(SessionContext);
  if (!session) {
    throw new Error("useSession must be used inside SessionBoundary");
  }
  return session;
}
