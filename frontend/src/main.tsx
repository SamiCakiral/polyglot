import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";

import { AppProviders } from "./app/providers";
import { createAppQueryClient } from "./app/query-client";
import { createAppRouter } from "./app/router";
import "./app/styles.css";

async function enableContractMocks(): Promise<void> {
  if (!import.meta.env.DEV || import.meta.env.VITE_ENABLE_API_MOCKS !== "true") {
    return;
  }

  const { worker } = await import("./lib/mocks/browser");
  await worker.start({ onUnhandledRequest: "error" });
}

await enableContractMocks();

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Missing #root application mount point");
}

const queryClient = createAppQueryClient();
const router = createAppRouter();

createRoot(rootElement).render(
  <StrictMode>
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>
  </StrictMode>,
);
