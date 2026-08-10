import {
  Navigate,
  createBrowserRouter,
  createMemoryRouter,
  type RouteObject,
} from "react-router-dom";

import { AppShell } from "./app-shell";
import { shellRoutes } from "./navigation";
import { RouteErrorBoundary } from "./route-error-boundary";
import { NotFoundRoute, ShellRoute } from "./shell-route";
import { SessionBoundary } from "./session";

const routes: RouteObject[] = [
  {
    path: "/",
    element: (
      <SessionBoundary>
        <AppShell />
      </SessionBoundary>
    ),
    errorElement: <RouteErrorBoundary />,
    children: [
      { index: true, element: <Navigate replace to="/today" /> },
      ...shellRoutes.map(({ path, title }) => ({
        path,
        element: <ShellRoute title={title} />,
      })),
      { path: "*", element: <NotFoundRoute /> },
    ],
  },
];

export function createAppRouter(initialEntries?: string[]) {
  if (initialEntries) {
    return createMemoryRouter(routes, { initialEntries });
  }

  return createBrowserRouter(routes);
}
