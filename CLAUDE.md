# LurkMoar

Read-only 4chan reader for Omarchy (PySide6). **Start with `HANDOFF.md`**: it has the current state, the next step and the cautions.

- Spec: `docs/superpowers/specs/2026-10-03-lurkmoar-design.md`
- Plan: `docs/superpowers/plans/2026-10-03-lurkmoar.md`
- Never add POST/PUT/DELETE or any posting feature. Keep dependencies to PySide6 and httpx.
- Tests: `.venv/bin/pytest` (offscreen Qt, fake network only).
