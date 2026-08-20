# Stable testbed controllers

All verdict logic is versioned here. Self-hosted runners provide only a transport executable through `PM_TESTBED_TRANSPORT`; it receives a repository-defined JSON request and must return raw observations. The controller independently locates the exact APKs from the selected build run, verifies their hashes, binds the exact Rill adapter, validates gate-specific semantics, and emits `PASS` only after the repository validator accepts the result. Missing transport or infrastructure is `BLOCKED`/job failure, never synthetic evidence.
