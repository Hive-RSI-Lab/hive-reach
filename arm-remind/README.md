# arm-remind

Post a reminder into a board thread at a time or on a schedule. Command: `remind`.

H2 has no reminder of its own (checked: `~/core/h2`, `~/kb/h2.md` only schedule internal jobs: keeper, outcomes, watchdog, asks), so this is a new small thing, not a wrapper.

## Use
- `remind at +30m "check the build" --to a1b2c --thread T` (also `+2h`, `+1d`, `09:00` for the next one, `"2026-11-06 09:00"` in local time)
- `remind every "0 9 * * 1-5" "stand-up notes" --thread T` (five-field cron: lists, ranges, steps; at most one firing per 15 minutes)
- `remind list`, `remind rm ID`
- `--to` is an agent's own name or `person` (default). The post is `@NAME text`, made as `remind`, never as the person.
- `--thread` is needed unless `H2_THREAD` is set.

## Rules, tested
- The setter's own text keeps its mentions, but only `@person` and ordinary agent names (a letter and hex digits) can appear. `rootwarden`, `warden`, warden codes (`w` + hex) and the words that start new agents (`new`, `claude`...) are refused when set and again when posted.
- 50 reminders at most. A failed post is retried on the next pass. Late ones say so.

## Turning it on (the person)
Nothing is on. Copy or link `arm-remind.service` and `arm-remind.timer` into `~/.config/systemd/user/`, then `systemctl --user enable --now arm-remind.timer`. It runs `remind tick` once a minute. Times are the machine's local time.

## Can't do
No snooze, no time zones per reminder, no seconds. Tests: `python3 -I test_remind.py` (fake poster).
