## What and why

<!-- The behaviour change and the reason for it. Link issues as owner/repo#123. -->

## How it was verified

- [ ] `make check` (ruff, mypy, pytest, tsc, vitest, Playwright, IaC check)
- [ ] API schema changed → `make openapi`, both generated files committed
- [ ] UI changed → checked at 390 px and 1440 px, dark and light theme
- [ ] Deployment files changed → production images build and `make smoke` passes against `make up`

## Project rules

- [ ] Money stays integer minor units; ids stay opaque strings
- [ ] No synthetic ground truth reaches the runtime database or detector input
- [ ] UI copy through `i18n.ts`, styling through `tokens.css`
- [ ] Any metric quoted comes from an executed, committed benchmark run

## Risk and rollback

<!-- Migrations? Data shape changes? How to roll back? -->
