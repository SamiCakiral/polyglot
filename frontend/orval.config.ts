import { defineConfig } from "orval";

export default defineConfig({
  polyglot: {
    input: {
      target: "../contracts/openapi/v1.json",
    },
    output: {
      target: "./src/generated/polyglot.ts",
      schemas: "./src/generated/model",
      client: "react-query",
      httpClient: "fetch",
      mock: {
        path: "./src/generated/mocks",
        indexMockFiles: true,
        generators: [
          { type: "msw", delay: 0 },
          { type: "faker" },
        ],
      },
      clean: true,
      formatter: "prettier",
    },
  },
});
