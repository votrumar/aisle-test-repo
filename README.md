# aisle-test-repo

Sample Python project with a deliberately vulnerable dependency, used to
exercise Aisle's SCA pipeline (PLA-857: retriage IGNORED/DISMISSED issues
when new findings arrive).

## Vulnerable dependency

- `Pillow==8.1.0` — multiple CVEs in image decoders (TIFF, ICNS, SGI, BLP).
  Examples: CVE-2021-25287, CVE-2021-25288, CVE-2021-27921, CVE-2021-27922,
  CVE-2021-27923.

## Why the vulnerable code is NOT reachable

`src/sample/main.py` uses Pillow strictly to *generate* PNGs in memory:

```python
img = Image.new("RGB", (width, height), color=color)
img.save(buf, format="PNG")
```

It never calls `Image.open` or any other entry point that touches an image
decoder, so none of the CVEs above are reachable from application code.
Aisle's triage should mark the SCA finding as not relevant.

## Workflow under test

1. Import the repo into Aisle and run Snyk SCA. Triage marks the issue
   "not relevant" / dismisses it (no vulnerable code path).
2. Downgrade the dep further (e.g. `Pillow==7.0.0`) to surface additional
   CVEs.
3. Re-run the Snyk import. The previously dismissed issue must
   automatically re-triage with reason "A new finding has been detected:
   CVE-...".
