import type { ReactNode } from "react";

import { AppShell } from "./app-shell";
import { ProfileProvider } from "./profile-context";
import { SessionBoundary } from "./session";

export function ProtectedShell() {
  return (
    <SessionBoundary>
      <ProfileProvider>
        <AppShell />
      </ProfileProvider>
    </SessionBoundary>
  );
}

export function ProtectedFocus({ children }: { children: ReactNode }) {
  return (
    <SessionBoundary>
      <ProfileProvider>{children}</ProfileProvider>
    </SessionBoundary>
  );
}
