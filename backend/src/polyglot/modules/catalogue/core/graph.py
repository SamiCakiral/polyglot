from collections import deque
from dataclasses import dataclass
from uuid import UUID

from polyglot.modules.catalogue.core.domain import (
    PrerequisiteEdgeType,
    SkillPrerequisiteEdge,
    SkillRevision,
)
from polyglot.platform.errors import DomainError, ErrorCode


@dataclass(frozen=True, slots=True)
class TraversalResult:
    skill_revision_ids: tuple[UUID, ...]
    depth_reached: int
    truncated: bool


class SkillGraph:
    def __init__(
        self,
        skills: tuple[SkillRevision, ...],
        edges: tuple[SkillPrerequisiteEdge, ...],
    ) -> None:
        self._skills = {skill.skill_revision_id: skill for skill in skills}
        if len(self._skills) != len(skills):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="duplicate skill revision")
        edge_ids = {edge.edge_id for edge in edges}
        edge_keys = {
            (edge.from_skill_revision_id, edge.to_skill_revision_id, edge.edge_type)
            for edge in edges
        }
        if len(edge_ids) != len(edges) or len(edge_keys) != len(edges):
            raise DomainError(ErrorCode.VALIDATION_FAILED, detail="duplicate prerequisite edge")
        for edge in edges:
            if (
                edge.from_skill_revision_id not in self._skills
                or edge.to_skill_revision_id not in self._skills
            ):
                raise DomainError(ErrorCode.REFERENCE_NOT_FOUND)
        self.edges = tuple(
            sorted(
                edges,
                key=lambda item: (
                    str(item.from_skill_revision_id),
                    str(item.to_skill_revision_id),
                    item.edge_type.value,
                ),
            )
        )
        self._required_incoming: dict[UUID, tuple[UUID, ...]] = {}
        required_outgoing: dict[UUID, list[UUID]] = {
            skill_revision_id: [] for skill_revision_id in self._skills
        }
        incoming: dict[UUID, list[UUID]] = {
            skill_revision_id: [] for skill_revision_id in self._skills
        }
        for edge in self.edges:
            if edge.edge_type is not PrerequisiteEdgeType.REQUIRED:
                continue
            required_outgoing[edge.from_skill_revision_id].append(edge.to_skill_revision_id)
            incoming[edge.to_skill_revision_id].append(edge.from_skill_revision_id)
        self._required_incoming = {
            node: tuple(sorted(prerequisites, key=str))
            for node, prerequisites in incoming.items()
        }
        self._assert_required_acyclic(required_outgoing)

    def _assert_required_acyclic(self, outgoing: dict[UUID, list[UUID]]) -> None:
        indegree = dict.fromkeys(outgoing, 0)
        for targets in outgoing.values():
            for target in targets:
                indegree[target] += 1
        ready = [node for node, count in indegree.items() if count == 0]
        ready.sort(key=str, reverse=True)
        visited = 0
        while ready:
            node = ready.pop()
            visited += 1
            for target in sorted(outgoing[node], key=str):
                indegree[target] -= 1
                if indegree[target] == 0:
                    ready.append(target)
                    ready.sort(key=str, reverse=True)
        if visited != len(outgoing):
            raise DomainError(ErrorCode.PREREQUISITE_CYCLE)

    def prerequisites_for(
        self,
        skill_revision_id: UUID,
        *,
        max_depth: int,
        max_nodes: int,
    ) -> TraversalResult:
        if skill_revision_id not in self._skills:
            raise DomainError(ErrorCode.REFERENCE_NOT_FOUND)
        if max_depth < 0 or max_nodes < 1:
            raise DomainError(ErrorCode.VALIDATION_FAILED)

        queue: deque[tuple[UUID, int]] = deque(
            (node, 1) for node in self._required_incoming[skill_revision_id]
        )
        visited: set[UUID] = set()
        result: list[UUID] = []
        depth_reached = 0
        truncated = False
        while queue:
            node, depth = queue.popleft()
            if node in visited:
                continue
            if depth > max_depth:
                truncated = True
                continue
            if len(result) >= max_nodes:
                truncated = True
                continue
            visited.add(node)
            result.append(node)
            depth_reached = max(depth_reached, depth)
            queue.extend(
                (prerequisite, depth + 1)
                for prerequisite in self._required_incoming[node]
                if prerequisite not in visited
            )
        return TraversalResult(tuple(result), depth_reached, truncated)
