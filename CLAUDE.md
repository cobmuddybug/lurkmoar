# LurkMoar

Read-only imageboard reader for Omarchy (PySide6). See `README.md` for usage and `docs/design/` for the design specs.

- Never add POST/PUT/DELETE or any posting feature: the API client exposes `get()` and `close()` only, and a test greps `src/` for write verbs.
- Runtime dependencies stay `PySide6` and `httpx`. Only `api.py` imports httpx.
- Tests: `.venv/bin/pytest` (offscreen Qt, fake network only). Never hit real sites from automated tests.
- Sites live in `src/lurkmoar/sites.json`; a new site that fits an existing family is one entry there.
