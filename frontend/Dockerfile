FROM node:22.18.0-alpine AS build

RUN corepack enable && corepack prepare pnpm@11.16.0 --activate
WORKDIR /workspace
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml /workspace/frontend/
RUN pnpm --dir frontend install --frozen-lockfile
COPY contracts /workspace/contracts
COPY fixtures /workspace/fixtures
COPY frontend /workspace/frontend
RUN pnpm --dir frontend build

FROM nginx:1.29.4-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/frontend/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --retries=6 CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
