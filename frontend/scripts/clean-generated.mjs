import { rm } from "node:fs/promises";
import { resolve } from "node:path";

await rm(resolve("src/generated"), { force: true, recursive: true });
