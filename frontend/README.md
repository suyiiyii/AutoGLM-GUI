# Frontend Workspace

This directory contains the React/TypeScript frontend, built with TanStack Router and Tailwind-style UI utilities.

## Setup

```bash
cd frontend
pnpm install
```

## Development

```bash
cd frontend
pnpm dev
```

The dev server proxies API requests to `http://localhost:8080` when the backend is running locally via `uv run autoglm-gui`.

## Lint and type check

```bash
cd frontend
pnpm lint
pnpm type-check
```

Apply these before opening a PR to ensure ESLint and TypeScript are clean.

## Build

```bash
cd frontend
pnpm build
```

The bundled assets are consumed by the backend and Electron packaging scripts.
