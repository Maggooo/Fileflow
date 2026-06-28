# FileFlow

File organizer with a self-contained web UI. Single Python file, zero required
external dependencies (Pillow is optional, used only for EXIF photo dates).

## Running

```bash
python3 fileflow.py
```

Opens `http://127.0.0.1:7491` automatically. Ctrl+C to stop.

## Structure

Everything lives in [fileflow.py](fileflow.py) — there is no other source file:

- **Organizing logic** (`organizeaza`, `obtine_data_creare`, `hash_fisier`,
  `rezolva_conflict`, `colecteaza_fisiere`) — pure functions, no server
  dependency. This is where file-moving/copying/dedup/filtering behavior lives.
- **`HTML`** — the entire frontend (HTML/CSS/JS) as one triple-quoted string,
  served inline by the server. There is no separate static file or build step.
- **`Handler`** (`http.server.BaseHTTPRequestHandler` subclass) — routes
  `/`, `/scaneaza`, `/start`, `/progress`. See README.md's "How it works"
  section for the endpoint table.
- **`state`** — a single global dict shared between the request thread and
  the background worker thread spawned per `/start` call. There's no queue or
  lock; only one job can run at a time (`/start` returns 409 if already running).

## Conventions to preserve

- **Identifiers are Romanian** (`sursa`, `destinatie`, `metoda`, `sterge_mici`,
  `omit_duplicate`, etc.), and the UI text is Romanian. Keep new code
  consistent with this rather than mixing in English names.
- **No external deps in the core path.** Pillow is wrapped in
  `try/except ImportError` and gated behind `PIL_DISPONIBIL` — any new optional
  dependency should follow the same pattern, never a hard `import`.
- **Token auth**: `TOKEN = secrets.token_hex(16)` is generated once at process
  start and required (via `X-FileFlow-Token` header, checked with
  `secrets.compare_digest`) on state-changing/disclosing routes (`/start`,
  `/scaneaza`). New routes that read from the filesystem or trigger actions
  should be protected the same way; `/` and `/progress` are intentionally open
  since they don't accept attacker-controlled paths.
- Keep README.md's "How it works" endpoint table and "Run" command in sync
  whenever routes or the entry-point filename change — they drifted out of
  sync before (README referenced a nonexistent `organizator.py`).

## Testing changes

There's no test suite. Verify manually:
1. Run `python3 fileflow.py`, use the UI against a scratch source/destination
   folder.
2. Check `dry_run` mode reflects exactly what a real run would do.
3. Re-run against the same source/destination to confirm conflict resolution
   (`rezolva_conflict`) and duplicate detection (`omit_duplicate`) behave.
