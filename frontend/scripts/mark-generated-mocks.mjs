import { readdir, readFile, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";

const marker = "// @ts-nocheck -- Orval mock output is not exactOptionalPropertyTypes-safe.\n";
const mockFiles = ["polyglot.faker.ts", "polyglot.msw.ts"];

for (const filename of mockFiles) {
  const path = resolve("src/generated/mocks", filename);
  const source = await readFile(path, "utf8");
  if (!source.startsWith(marker)) {
    await writeFile(path, marker + source);
  }
}

async function collectNumberedCopies(directory) {
  const copies = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      copies.push(...(await collectNumberedCopies(path)));
      continue;
    }
    if (/ \d+\.ts$/.test(entry.name)) copies.push(path);
  }
  return copies;
}

const numberedCopies = await collectNumberedCopies(resolve("src/generated"));
if (numberedCopies.length > 0) {
  throw new Error(
    `Orval produced numbered collisions:\n${numberedCopies.join("\n")}`,
  );
}
