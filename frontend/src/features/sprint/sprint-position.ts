import type { SprintBlockResponse } from "../../generated/model";

export function resumeBlockOffset(
  blocks: SprintBlockResponse[],
  currentBlockId: string | null,
): number {
  const currentIndex = currentBlockId
    ? blocks.findIndex(
        (block) => block.session_plan_block_id === currentBlockId,
      )
    : -1;
  if (currentIndex >= 0) return currentIndex;

  const pendingIndex = blocks.findIndex(
    (block) => !["completed", "skipped", "abandoned"].includes(block.status),
  );
  return pendingIndex >= 0 ? pendingIndex : Math.max(0, blocks.length - 1);
}
