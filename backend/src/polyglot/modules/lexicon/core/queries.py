import base64
import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from polyglot.platform.errors import DomainError, ErrorCode


@dataclass(frozen=True, slots=True, order=True)
class WordBankItem:
    sense_id: UUID
    label: str
    lexical_order: int
    provenance_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WordBankPage:
    items: tuple[WordBankItem, ...]
    next_cursor: str | None
    reference_revision: str


@dataclass(frozen=True, slots=True)
class GraphEdge:
    source_sense_id: UUID
    target_sense_id: UUID
    edge_type: str


@dataclass(frozen=True, slots=True)
class Neighborhood:
    nodes: tuple[UUID, ...]
    edges: tuple[GraphEdge, ...]
    depth: int
    truncated: bool


def _cursor_payload(position: tuple[int, str], reference_revision: str) -> str:
    body = json.dumps(
        {"position": list(position), "reference_revision": reference_revision},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    envelope = body + b"." + hashlib.sha256(b"polyglot-wb-cursor-v1\0" + body).hexdigest().encode()
    return base64.urlsafe_b64encode(envelope).decode().rstrip("=")


def _decode_cursor(value: str, reference_revision: str) -> tuple[int, str]:
    try:
        padded = value + "=" * (-len(value) % 4)
        envelope = base64.urlsafe_b64decode(padded.encode())
        body, signature = envelope.rsplit(b".", 1)
        expected = hashlib.sha256(b"polyglot-wb-cursor-v1\0" + body).hexdigest().encode()
        payload = json.loads(body)
        position = payload["position"]
        valid = (
            signature == expected
            and payload["reference_revision"] == reference_revision
            and isinstance(position, list)
            and len(position) == 2
            and isinstance(position[0], int)
            and isinstance(position[1], str)
        )
        if not valid:
            raise ValueError
        return position[0], position[1]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, base64.binascii.Error) as error:
        raise DomainError(ErrorCode.CURSOR_INVALID) from error


def paginate_word_bank(
    source: tuple[WordBankItem, ...],
    *,
    limit: int,
    cursor: str | None,
    reference_revision: str = "encountered-v1",
) -> WordBankPage:
    if not 1 <= limit <= 100 or not reference_revision:
        raise DomainError(ErrorCode.FILTER_INVALID)
    ordered = tuple(sorted(source, key=lambda item: (item.lexical_order, str(item.sense_id))))
    after = None if cursor is None else _decode_cursor(cursor, reference_revision)
    if after is not None:
        ordered = tuple(
            item
            for item in ordered
            if (item.lexical_order, str(item.sense_id)) > after
        )
    page = ordered[:limit]
    has_more = len(ordered) > limit
    next_cursor = None
    if page and has_more:
        last = page[-1]
        next_cursor = _cursor_payload(
            (last.lexical_order, str(last.sense_id)), reference_revision
        )
    return WordBankPage(page, next_cursor, reference_revision)


def bounded_neighborhood(
    root: UUID,
    edges: tuple[GraphEdge, ...],
    *,
    depth: int,
    edge_types: frozenset[str],
    max_nodes: int = 500,
) -> Neighborhood:
    if not 1 <= depth <= 2 or not 1 <= max_nodes <= 500 or not edge_types:
        raise DomainError(ErrorCode.FILTER_INVALID)
    allowed = tuple(
        sorted(
            (edge for edge in edges if edge.edge_type in edge_types),
            key=lambda edge: (
                str(edge.source_sense_id),
                str(edge.target_sense_id),
                edge.edge_type,
            ),
        )
    )
    visited = {root}
    frontier = {root}
    included: list[GraphEdge] = []
    truncated = False
    for _ in range(depth):
        next_frontier: set[UUID] = set()
        for edge in allowed:
            if edge.source_sense_id not in frontier:
                continue
            if edge.target_sense_id not in visited and len(visited) >= max_nodes:
                truncated = True
                continue
            included.append(edge)
            if edge.target_sense_id not in visited:
                visited.add(edge.target_sense_id)
                next_frontier.add(edge.target_sense_id)
        frontier = next_frontier
        if not frontier:
            break
    return Neighborhood(tuple(sorted(visited)), tuple(included), depth, truncated)
