import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const marker = "// @ts-nocheck -- Orval mock output is not exactOptionalPropertyTypes-safe.\n";
const mockFiles = ["polyglot.faker.ts", "polyglot.msw.ts"];

for (const filename of mockFiles) {
  const path = resolve("src/generated/mocks", filename);
  const source = await readFile(path, "utf8");
  if (!source.startsWith(marker)) {
    await writeFile(path, marker + source);
  }
}
