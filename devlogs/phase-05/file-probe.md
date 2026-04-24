# Phase 05b File Send Probe

## Scope

- Add a manual file upload probe for QQ / OneBot-compatible adapters.
- Keep report generation and report delivery separated.
- Do not mark violation events as batched.
- Do not schedule automatic file delivery.

## Adapter API Assumption

Observed OneBot-compatible implementations expose group file upload as:

- action: `upload_group_file`
- params: `group_id`, `file`, `name`
- optional adapter-specific params such as `folder` are intentionally omitted.

This is treated as an implementation capability to probe, not as a guaranteed
core OneBot v11 capability.

References checked on 2026-04-24:

- LLOneBot documents `POST /upload_group_file` with `group_id`, `file`, `name`.
- NapLink documents `upload_group_file / upload_private_file` and
  `uploadGroupFile(groupId, file, name, folder?, uploadFile?)`.

## Command

```text
/cf file-probe [group]
.cf file-probe [group]
```

If `group` is omitted, the current group is used. The command writes a small
probe file under the plugin data directory and asks the platform action adapter
to upload it as `chat-filter-file-probe.txt`.

## Acceptance

1. Restart AstrBot and confirm the plugin loads.
2. Run `/cf probe`; on `aiocqhttp` with an action client, `send_file` should
   report `supported`.
3. Run `/cf file-probe <target_group_id>`.
4. The target group should receive `chat-filter-file-probe.txt`.
5. If the adapter rejects the action, the command should return a failed or
   unsupported status without affecting violation recording.

## Live Validation

Accepted on 2026-04-24:

- `/cf file-probe 1098085136` returned `Chat Filter file probe: success.`
- `/cf probe` returned `send_file=supported`.

## Hold

Automatic or scheduled report delivery is intentionally out of scope for this
plugin. A separate file/log reporter may consume generated report files.
