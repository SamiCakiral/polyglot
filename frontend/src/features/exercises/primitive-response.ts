import type { AnswerKind, JsonValueInput } from "../../generated/model";

export type PrimitiveResponse = JsonValueInput;

export function emptyResponse(kind: AnswerKind): PrimitiveResponse {
  switch (kind) {
    case "acknowledgement":
      return true;
    case "selection":
    case "tokens":
    case "ordered_items":
    case "spans":
      return [];
    case "pairing":
    case "grouping":
    case "cells":
    case "self_assessment":
      return {};
    case "no_answer":
      return null;
    default:
      return "";
  }
}

function clone(value: PrimitiveResponse): PrimitiveResponse {
  if (Array.isArray(value)) return value.map((item) => clone(item));
  if (typeof value === "object" && value !== null) {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, clone(item)]),
    );
  }
  return value;
}

export function normalizeResponse(
  kind: AnswerKind,
  value: PrimitiveResponse,
): PrimitiveResponse {
  if (kind === "tokens" && typeof value === "string") {
    return value
      .split(/[\s,;]+/u)
      .map((token) => token.trim())
      .filter(Boolean);
  }
  if ((kind === "text" || kind === "short_text") && typeof value === "string") {
    return value.trim();
  }
  return clone(value);
}

export function isResponseComplete(
  kind: AnswerKind,
  value: PrimitiveResponse,
): boolean {
  if (kind === "acknowledgement") return value === true;
  if (kind === "no_answer") return true;
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) {
    if (value.length === 0) return false;
    if (kind === "spans") {
      return value.every(
        (item) =>
          Array.isArray(item) &&
          item.length === 2 &&
          Number.isInteger(item[0]) &&
          Number.isInteger(item[1]) &&
          Number(item[0]) >= 0 &&
          Number(item[1]) >= Number(item[0]),
      );
    }
    return value.every((item) => typeof item === "string" && item.length > 0);
  }
  if (typeof value !== "object" || value === null) return false;
  const entries = Object.entries(value);
  return (
    entries.length > 0 &&
    entries.every(([, item]) => {
      if (typeof item === "string") return item.trim().length > 0;
      if (Array.isArray(item)) return item.length > 0;
      return item !== null;
    })
  );
}
