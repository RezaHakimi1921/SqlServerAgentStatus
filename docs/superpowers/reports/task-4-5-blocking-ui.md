# Tasks 4–5 — Blocking Tree UI + Humanized Wait Resource

## Status

Complete on `feat/blocking-tree-ui`.

- Blocking health strip now shows Blast radius, Head blockers, and formatted Chain age.
- Pair cards were replaced by one nested card per blocking root.
- Head blockers use critical styling; victims use warning styling with nested tree rails.
- Direct children after the first two are collapsed in native `html.Details`.
- SQL snippets retain modal controls.
- Unresolved wait resources use a UI-only humanized fallback; resolver semantics are unchanged.

## Commit

`feat: render blocking as nested trees with blast strip`

## Verification

```text
python -m pytest tests/test_wait_resource.py tests/test_blocking_tree.py tests/test_blocking_enrich.py tests/test_activity_blocking_layout.py -v
27 passed in 0.38s
```

IDE diagnostics reported no lint errors in the modified Python files.

## Concerns

- No live SQL Server snapshot was available for visual verification with real blocking chains.
- PAGE/RID resources remain display-only raw fallbacks when object resolution is unavailable, as allowed by the design.
