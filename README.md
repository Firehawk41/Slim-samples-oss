# slim-samples

The sample module of [SLIM](https://github.com/Firehawk41/slim-lims-oss), an ISO 17025 LIMS for an analytical
chemistry lab (OSS portfolio demo). A sample arrives in one or more bottles; slim-samples records how many and
what kind, their condition on receipt, where each is stored, how long it is kept, and when it is disposed of or
returned. A condition can warn on the report for just the analyses its bottle served, or block prep. The lab
sets its own lists and periods; every change is kept (append-only, with who and why).

A library: the host app composes it. See `docs/DECISIONS.md` and `CLAUDE.md`.
