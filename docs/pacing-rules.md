# Pacing rules against the usage cap

This page says what the seat pacing check reports and what each verdict asks of the owner. The check is report only: it reads logs and prints counts. It sends nothing, writes no file and touches no seat or service.

## Why the check exists

Every seat uses one model provider, and the seats appear to share one account (the log lines carry no account id, so this is inferred, not measured). When the provider refuses requests, the seat logs a `429` line with the type `rate_limit_error`. In one measured week the shared gateway logged 44 such lines; one seat held 32 of them, and 26 of those fell on a single day. The leaders (Claude Code runs) show the same pressure as a line reading "You've hit your N-hour limit", written into the run logs under the dispatch folder.

## The two classes, kept apart

The `rate_limit_error` lines carry two different causes, and the check counts them separately:

- Cap class: the account's usage cap. The message says the request would exceed the account's limit. This is pacing: the owner can only wait or space the work.
- Credit class: the fast-mode credit gate. The message says usage credits are required for fast mode. This is a billing setting, not the cap, and waiting does not clear it.

They are kept apart because a rule that counts the cap class alone misses the credit class. In the measured week one seat (hades) logged 6 lines on one day, all credit class; a cap-only rule reads that seat as quiet. A 429 `rate_limit_error` line that is not the credit class is counted as cap class.

The delegate line ("rate-limited every one of 3 attempts") is not counted: it repeats a cap or credit line already counted from the same log.

## Verdicts

Thresholds are constants at the top of the script: SLOW at 1 cap-class line, PAUSE at 5, inside the window (default 24 hours).

| Verdict | When | What it asks of the owner |
|---|---|---|
| OK | no cap-class line and no credit-class line in the window | nothing |
| SLOW | cap-class count reaches 1 | space the dispatches on that seat: no new dispatch while one is running there |
| PAUSE | cap-class count reaches 5 | no new work on that seat until the reset time (the leader lines carry the reset time; the seat logs do not) |
| CREDIT | credit-class count above 0 and the cap verdict is OK | a billing setting (fast-mode credits): fix it in the account, or turn fast mode off. Not pacing |
| ABSENT | the seat's agent log does not exist | not an error; nothing is counted |

When both classes are present, the cap verdict wins (SLOW or PAUSE) and the credit count is still printed.

The leader row applies the same SLOW and PAUSE thresholds to the "hit your N-hour limit" lines found in run logs whose modification time falls in the window. It has no credit count.

## What it reads

The agent log of each of five seats (hub, hades, hephaestus, poseidon, zeus): the hub's is `logs/agent.log` under the Hermes home, the others `profiles/<seat>/logs/agent.log`. The leader run logs are the `.log` files directly inside the dispatch folder. Only fixed patterns are matched and only counts are kept: no line text is printed, stored or returned.

## How to run it

From the kit, with the interpreter on its own line and the script path next to it:

    python hephaestus/scripts/seat_pacing_check.py

Output is one row per seat and one leader row (`seat=<name> cap=<n> credit=<n> verdict=<V>`), then a total line. Exit codes: 0 when every row is OK or ABSENT, 1 when any row is SLOW, PAUSE or CREDIT, 2 when a log that exists cannot be read.

Overrides (environment variables): `SEAT_PACING_HOME` replaces the Hermes home, `SEAT_PACING_DISPATCH` the dispatch folder, `SEAT_PACING_HOURS` the window in hours, `SEAT_PACING_NOW` a fixed "now" in ISO form (used by the test).

The fixture test is `tests/test_seat_pacing_check.py`. It builds synthetic logs and checks each verdict, the window, the leader row, the absent row, the unreadable exit and that no line text reaches the output.

## Limits

The check reports; the owner decides. It does not pause a seat, edit a config, send a message or read an account. The window and thresholds are starting values to be tuned against the next measured week.
