# Phase 05a Report Dry Run

## Scope

Phase 05a adds local violation history report generation.

This phase includes:

- `/cf report-dry-run [group] [days]` and `.cf report-dry-run [group] [days]`;
- a repository query for unbatched violation records in a scoped time window;
- local TSV report generation under the plugin data directory;
- validation of group id and report day range.

This phase does not include:

- background scheduling;
- sending files to QQ;
- calling OneBot or NapCat file upload APIs;
- creating or marking `violation_batches`;
- updating `violation_events.file_batch_id`.

## Data Boundary

The report file is generated under:

```text
data/astrbot_plugin_chat_filter/reports/
```

Generated reports are runtime artifacts. They must not be written into the
source tree.

The report query is scoped by:

- platform;
- listening group id;
- UTC window start;
- UTC window end;
- `file_batch_id IS NULL`.

The dry-run command does not mutate report batch state, so repeated runs may
include the same unbatched rows.

## Report Content

The TSV file contains:

- created time;
- listening group id;
- masked sender id;
- sender display-name snapshot;
- matched keyword;
- matched content excerpt;
- mute status;
- recall status;
- forward status.

The sender id is masked in the generated file. Full ids remain in SQLite for
audit joins.

The command response only returns the record count, generated file name, and
window bounds. It does not echo report contents to QQ.

## Manual Acceptance

Preconditions:

1. The plugin has violation records in SQLite.
2. The command sender has AstrBot admin permission.

Steps:

1. Run `/cf report-dry-run <listening_group_id> 7`.
2. Confirm the command returns:

```text
Chat Filter report dry-run generated: records=<n>, file=<name>, window=<start>..<end>.
```

3. Open the generated file under `data/astrbot_plugin_chat_filter/reports/`.
4. Confirm the file is TSV and includes only the requested listening group.
5. Confirm sender ids are masked in the file.
6. Confirm no source-tree file is generated.

SQLite check:

```sql
SELECT id, platform, group_id, user_id, matched_keyword,
       action_mute_status, action_recall_status, action_forward_status,
       file_batch_id, created_at
FROM violation_events
WHERE group_id = '<listening_group_id>'
ORDER BY id DESC
LIMIT 10;
```

The dry-run report should not change `file_batch_id`.

## Scope Update

Phase 05b confirmed the target adapter file-upload API with a manual
file-send probe.

Scheduled report delivery is skipped in this plugin. The chat filter plugin
keeps producing local report files; any generic interval-based file delivery
should be implemented outside this plugin.
