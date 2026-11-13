# arm-calendar

Read the person's calendar. Command: `cal`.

## Setup (the person's steps)
Get the private ICS link from the calendar (Google: Settings > the calendar > "Secret address in iCal format"; iCloud and Fastmail have a public/shared ICS link). Save it in the dashboard's secret box as `conn-calendar`. For a password-protected ICS file, save JSON instead: `{"url": "...", "user": "...", "password": "..."}` (sent as Basic auth). The link is itself a secret, so it must be `https://` or `webcal://`; a plain `http://` one is refused unless the JSON says `"allow_http": true`.

## Use
`cal today`, `cal next [N]`, `cal agenda [DAYS]` (default 7). `--file F.ics` reads a file. Times show in the machine's zone.

## Rules, tested
- Event titles, places and notes are outside text: mentions are stripped, control characters dropped, and the output starts with a line saying it is data. Notes aren't printed at all.
- The link is a secret: errors never include it. http(s) and webcal only. 5 MB cap.
- Read-only: no function in `cal.py` sends anything but a GET (a test checks the source for write verbs).

## Why it can't write
Adding or changing events is not built. A calendar write is the person's act in front of other people (invites go out under their name, and a move can't be recalled), and the ICS link can't write in any case. If it is wanted, it would be a separate, off-by-default step with its own allow-list, like `arm-homeassistant`, and a warden look first.

## Parser
Own small parser (standard library only, `zoneinfo` for TZID): folded lines, all-day events, DURATION, EXDATE, cancelled events, moved single instances (RECURRENCE-ID), and RRULE with FREQ DAILY/WEEKLY/MONTHLY/YEARLY, INTERVAL, COUNT, UNTIL, BYDAY (with a number for monthly: `1FR`, `-1FR`), BYMONTHDAY, BYMONTH. Times follow the event's own zone across daylight saving. Not handled: BYSETPOS, BYWEEKNO, BYYEARDAY, hourly/minutely rules (only the first event of those shows), RDATE. `"python": ["icalendar","recurring-ical-events"]` would cover these; not worth a dependency until one of them is needed.

## CalDAV
Not built. Most CalDAV servers (Fastmail, Nextcloud, iCloud) also give an ICS link, which this reads.

Tests: `python3 -I test_cal.py` (local fake server; no internet).
