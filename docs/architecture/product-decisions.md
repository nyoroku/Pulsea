# Product Architecture Decisions

Status: Accepted baseline for implementation
Accepted: 2026-05-31

These decisions lock the recommended defaults from `IMPLEMENTATION_BACKLOG.md`.
Change a decision through a follow-up ADR before changing schema or workflow
behavior.

| ID | Decision |
| --- | --- |
| DEC-01 | A post is `PUBLISHED` when at least one target publishes and all targets are terminal. It is `FAILED` only when no target publishes. |
| DEC-02 | A content request targets multiple platforms through normalized `ContentRequestTarget` rows. |
| DEC-03 | Clients use deactivation plus `deleted_at`; historical relationships remain available and inactive clients lose portal access. |
| DEC-04 | Media uses `deleted_at`; deleted assets disappear immediately and storage objects are purged after 30 days. |
| DEC-05 | First-comment status, error, remote ID, and sent timestamp are stored per `PostTarget`. |
| DEC-06 | Analytics use timestamped per-target snapshots. |
| DEC-07 | Post changes, reschedules, retries, and publish transitions are recorded in a dedicated audit table. |
| DEC-08 | X trends are optional behind a provider interface; Google Trends, RSS, and manual signals remain available without X. |
| DEC-09 | Instagram starts with private S3 URLs. Add narrowly scoped temporary delivery objects only if Meta fetch testing proves they are required. |
| DEC-10 | Each portal user belongs to exactly one client in V1. |
