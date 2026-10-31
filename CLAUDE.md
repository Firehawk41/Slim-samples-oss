# slim-samples — Claude context

> **Read first.** Jamie is the **designer**; Claude writes the code, then explains it until Jamie can defend
> every decision in an interview. Raise any design change as a new decision (with a recommendation) before
> building it; push back when you disagree. **Short replies; Jamie is token-constrained.** Log who decided
> what in slim-lims-oss `docs/DEV_DIARY.md`. Read slim-lims-oss's CLAUDE.md for the ecosystem's rules; this
> repo follows them.

## What this is

The **sample module** of SLIM (roadmap phase 4, ISO 17025 §7.4): the bottles a sample arrives in, their
condition on receipt, where they are, how long they are kept and what happened to them. A **library**:
slim-lims-oss calls it, owns the transaction and provides the screens. **OSS sandbox only:** demo data, never
a real lab's databases (`persistence/oss_guard.py`).

## Documents

| File | What |
|---|---|
| `docs/DECISIONS.md` | **Authoritative.** S-01…S-11; append, never edit history. |

## File map

```
slim_samples/
├── domain/        # pure (stdlib + pydantic): base (Frozen), actor (Role, IdentitySource), rules (SamplesRules: container
│                  #   kinds, conditions with an Effect, locations, disposal methods, retention), containers (ContainerIn,
│                  #   Container with derived state, events, flags, blocked, plan_receipt, labels, SampleLookup port), problems
├── persistence/   # oss_guard, db (make_engine = the only create_engine), migrate, migrations/, types, append_only, audit,
│                  #   tables (samples_rules / _containers / _events), rules (publish_rules, current_rules), store (insert, load)
├── service/       # custody: receive, add_container, move, note_conditions, correct, hold, release_hold, dispose,
│                  #   return_to_customer, reading (containers_of / _for, due_for_disposal, flags_for, blocked_for, labels_for),
│                  #   verify; rules
└── demo.py        # DEMO_RULES: invented lists the host seeds
tests/             # factories; domain/; service/; architecture, OSS guard, migrations
.github/workflows/ci.yml  # ruff + {SQLite, Postgres 16} × {3.11, 3.12} + 95% branch coverage on domain
```

Run: `pip install -e ".[dev]" && pytest -q -p no:warnings`; `ruff check . && ruff format --check .`.

## Rules for the build

- `domain/` imports only stdlib + pydantic; `tests/test_architecture.py` enforces it, and that no other SLIM
  module is imported anywhere (roadmap rule 2).
- Lists, effects and periods are lab **data** (`SamplesRules`), never `if demo:` branches.
- Append-only: no update path in the code, triggers in the database. State is derived by folding events.
- Table names start `samples_`. Portable schema (SQLite + Postgres): enums as ints, JSON, no ARRAY, no FKs
  into other modules' tables. Services flush; the caller commits.
- Every push: ruff, full tests, coverage gate.
