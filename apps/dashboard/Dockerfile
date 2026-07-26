# NavIC dashboard image (Next.js 14). Build context is apps/dashboard.
# The API base URL is a build arg because Next.js inlines NEXT_PUBLIC_* at build
# time; all pages fetch the API from the browser, so this is the host-published
# API URL (default http://localhost:8000), not a container-internal hostname.
FROM node:22-slim AS build

WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN corepack enable

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . ./
RUN pnpm build

EXPOSE 3000
CMD ["pnpm", "start"]
