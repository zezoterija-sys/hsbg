# Recycle bin

Historical project files live here instead of being permanently deleted.

These files are **not active code**. They may describe older prototypes,
obsolete APIs, superseded tests, or integration notes that no longer match the
current architecture.

Rules:

- Active code must not import from `recycle_bin/`.
- Active tests live only under the root `tests/` directory.
- If an old implementation becomes useful again, reintroduce the relevant idea
  into the current architecture rather than importing the historical file
  directly.
- Files may be removed from the recycle bin later only as a deliberate cleanup.
