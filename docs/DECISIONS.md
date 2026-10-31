# slim-samples decisions

Authoritative. Append; never edit history. Jamie decides, Claude recommends. The ecosystem's log is
slim-data-oss `docs/DECISIONS.md` (D-120 records this module); who decided what is in slim-lims-oss
`docs/DEV_DIARY.md`.

- **S-01 A module of its own** (Jamie, 2026-10-31, roadmap phase 4). Options: host tables only; fold it into
  slim-prep; a new library. Chosen: a library, `slim-samples-oss`, as slim-prep is (roadmap rule 4). It owns
  the bottles; the TR stays the host's and prep stays the prep book's.
  - Rejected: host tables (the host does no department's work, rule 3); in slim-prep (receiving a sample is
    not prepping it, and slim-prep would need to know about custody).

- **S-02 The unit is the container, not the sample** (Jamie, 2026-10-31). A sample arrives in one or more
  bottles of different kinds (PFA, HDPE, glass). Each row says kind, how many, where it is stored, its
  condition on receipt and which analyses it serves (none named: all ordered). A sample must have at least one
  row before check-in completes on the screen.
  - Rejected: a condition per sample (a leaking HDPE bottle must not mark the analysis run from the intact
    PFA one); one row per physical bottle (a count does the same job).

- **S-03 The lab owns the lists** (Jamie: "customizable for the lab"). Container kinds, conditions, storage
  locations, disposal methods and the retention period (with a per-customer override) are data in
  `SamplesRules`, published as numbered, content-hashed, immutable versions by quality or a supervisor. A
  container records the version it was received under.
  - Rejected: enums in code; editing a list in place (it would rewrite what a past bottle meant).

- **S-04 What a condition does** (Jamie). Each condition has an effect: *recorded only*, *warn* (the review
  screen and the issued report say the analysis may be compromised, only for the analyses the bottle serves)
  or *block* (no prep batch takes the sample until the lab acts). Default for "leaking": warn. The effect is
  copied onto the bottle when the condition is noted, so changing the lab's list never rewrites a past report.
  The host composes the warning and the block; the modules do not import each other.
  - Rejected: blocking by default (Claude's first proposal; Jamie: leaking only warns); raising a
    nonconformity from a condition by itself (slim-data D-113: no nonconformity from a flag alone).

- **S-05 Receipt is one record, custody is events** (Claude). What was received is a row never changed.
  Moves, condition notes, corrections, holds, disposal and return are appended events; location, state and
  "held" are derived by folding them. A finished bottle (disposed or returned) takes no more events.

- **S-06 Labels** (Jamie, "labels" in §7.4). A printable page per request: code `TR00042-01/2`, kind, count,
  received date, keep-until date. The code is unique per bottle, so a barcode can be added later. No barcode
  now.

- **S-07 Tables** (Claude, as slim-prep P-19). `samples_rules`, `samples_containers`, `samples_events`; its
  own Alembic version table; append-only by trigger on SQLite and Postgres; portable (enums as ints, JSON, no
  foreign key into another module's tables; the sample is the lab sample ID as text).

- **S-08 Reasons** (Claude). A reason is required to change a condition, correct a count / kind / analyses,
  put a bottle on hold, lift a hold, or dispose of a bottle before its retention date. Lifting a hold needs a
  supervisor or quality.

- **S-09 Retention is a date, not a timer** (Jamie asked; Claude explained and Jamie accepted). Keep-until =
  received date + the lab's days (or the customer's override). The board and `/samples` list bottles due and
  overdue; nothing is disposed of automatically: a person records "disposed" (method from the lab's list) or
  "returned to the customer". A hold keeps a bottle off the due list (open complaint, nonconformity).
  - Rejected: automatic disposal; a background job.

- **S-10 Check-in is composed by the host** (Claude, Jamie agreed). The host's check-in (receipt, chemical
  matching, status) and the bottles of every sample are one transaction; the check-in screen requires them.
  The machine contract (spec §12) is unchanged, so the API accepts bottles but does not require them, and
  `/samples/log/{tr}` logs them afterwards.
  - Rejected: moving the TR transition into slim-samples (the TR and the reference data are the host's,
    roadmap rules 2 and 3; slim-samples can hold no foreign key into them).

- **S-11 Parked** (Claude, for Jamie): a rules editor beyond JSON; barcodes; the customer stating on the
  request form how many bottles they send (to flag "expected 3, received 2"); a nonconformity opened from a
  condition by a person (D-113 allows it, there is no button yet).
