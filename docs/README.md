# Docs Workspace

This directory hosts the Docusaurus site that powers the AutoGLM-GUI documentation portal.

## Install

```bash
cd docs
pnpm install
```

pnpm manages the Node toolchain for building, developing, and deploying the docs.

## Development

```bash
cd docs
pnpm start
```

The dev server runs locally and watches for MDX/TSX changes.

## Build

```bash
cd docs
pnpm build
```

The static output lands in `docs/build`.

## Deployment

```bash
cd docs
USE_SSH=true pnpm deploy
```

Set `GIT_USER=<GitHub username>` instead if you deploy without SSH.
