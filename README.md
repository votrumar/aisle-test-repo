# aisle-test-repo

Sample Python project with a deliberately vulnerable dependency, used to
exercise Aisle's SCA pipeline (PLA-857: retriage IGNORED/DISMISSED issues
when new findings arrive).

## Dependency note

This repo previously pinned `requests==2.19.0` (affected by CVE-2018-18074: `requests` could leak an `Authorization` header on cross-origin redirect). It has been upgraded to `requests==2.33.0`.

## Workflow under test

1. Import this repo into Aisle, run Snyk SCA. Issue created for `requests`.
2. Dismiss the issue.
3. Downgrade `requests` further (e.g. `2.18.0`) to surface additional CVEs.
4. Re-run Snyk import. Dismissed issue should automatically retriage with
   reason "A new finding has been detected: CVE-...".
