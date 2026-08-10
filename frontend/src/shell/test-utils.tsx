import { QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { RouterProvider } from "react-router-dom";

import { AppProviders } from "../app/providers";
import { createAppRouter } from "../app/router";

export function renderShell(path = "/today") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  const router = createAppRouter([path]);
  const view = render(
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>,
  );

  return { ...view, queryClient, router };
}

export function renderWithErrorBoundary(element: ReactElement) {
  const queryClient = new QueryClient();
  return render(<AppProviders queryClient={queryClient}>{element}</AppProviders>);
}
