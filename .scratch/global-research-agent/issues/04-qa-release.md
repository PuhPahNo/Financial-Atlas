# QA and release

Status: ready-for-human

Run automated tests, hard real-key query QA under the USD 10 cap, responsive browser QA, push main, and verify the exact Render revision.

## Comments

- `make verify` passed with 169 backend tests, 71.93% coverage, lint, TypeScript, zero duplicate clones, and the optimized Next.js build before the final argument-validation hardening.
- Targeted post-review tests passed; the full release gate is rerun immediately before committing.
- Render remains the existing Starter Docker service with one instance and one 1 GB disk. Model, rate, USD 25 global cap, USD 10 QA sub-cap, and production usage mode are explicitly configured on that service.
