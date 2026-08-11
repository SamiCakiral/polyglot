import type { CurrentSessionResponse, ProblemResponse } from "../generated/model";
import { uuid7 } from "./ids";

export function commandFetch(
  session?: CurrentSessionResponse,
  version?: number,
): RequestInit {
  const headers: Record<string, string> = {
    "Idempotency-Key": uuid7(),
  };

  if (session) {
    headers["X-CSRF-Token"] = session.csrf_token;
  }
  if (version !== undefined) {
    headers["If-Match"] = `"${String(version)}"`;
  }

  return { credentials: "include", headers };
}

export function queryFetch(): RequestInit {
  return { credentials: "include" };
}

export function responseProblem(response: { data: unknown; status: number }): string {
  if (response.status >= 200 && response.status < 300) {
    return "";
  }

  const problem = response.data as Partial<ProblemResponse>;
  return problem.detail ?? problem.title ?? "La demande n'a pas pu aboutir.";
}

export function todayIso(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Paris",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}
