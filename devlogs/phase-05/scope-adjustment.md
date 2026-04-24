# Phase 05 Scope Adjustment

## Decision

Scheduled file delivery is skipped for this plugin.

This plugin keeps ownership of:

- violation detection;
- mute, recall, merged-forward, and text-log actions;
- structured violation records;
- manual report generation;
- manual file-upload probing.

This plugin does not own:

- generic interval-based log file delivery;
- per-target-group file delivery schedules;
- scanning arbitrary plugin log folders;
- retrying scheduled file delivery jobs.

## Config Cleanup

The unused `report_files_enabled` setting was removed.

The report default is now named `default_report_days`, because it only controls
the default time window for manual report generation. The legacy
`default_report_interval_days` key remains accepted by `settings.py` as a
fallback for existing local config.

## Next Development Direction

Continue with non-scheduler work inside this plugin, such as:

- operator-facing query commands for recent violation records;
- report file cleanup controls;
- command output wording and acceptance docs;
- persistence boundary cleanup if `repository.py` keeps growing.
