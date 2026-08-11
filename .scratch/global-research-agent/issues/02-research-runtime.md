# Bounded research runtime

Status: ready-for-human

Implement the Responses API tool loop, strict read-tool schemas, page context, grounded artifact generation, and persistence while preserving confirmed paper-trading writes.

## Comments

- Added the Responses API tool loop over strict, independently validated read-only tools; no SQL or database credentials are exposed.
- Tool outputs generate the model context and the displayed artifacts from the same normalized objects.
- Hard QA covered multi-company cash flow, ETF price risk, page-context resolution, screening, and valuation reconciliation.
