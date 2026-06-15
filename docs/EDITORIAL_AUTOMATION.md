# PTIA Editorial Automation

## Objective

Prepare complete news packages in the dashboard queue `A Rever`. The automation
never approves, schedules, edits Buffer posts, or touches the LinkedIn comments
engine.

## Production flow

1. GitHub Actions runs at 18:00 Europe/Lisbon on weekdays.
2. Gemini discovers candidates and the source verifier checks URL, source and date.
   The daily scout prioritizes news published that day. A story from the previous
   day is accepted only when grounded evidence shows that it is still gaining
   momentum today.
3. The engine scores candidates with a fixed portfolio policy:
   - 55% editorial value;
   - 25% estimated engagement;
   - 10% freshness;
   - 10% portfolio fit.
4. Historical performance can adjust engagement by at most 8 points. With
   insufficient samples the adjustment is zero.
5. The selection includes an explicit Portugal story when a qualified one exists
   and limits concentration to two stories per source or category.
6. A Fact Pack is created before any copy. Generic or insufficient packs fail.
7. LinkedIn, Instagram, site and optional X copy is generated from the Fact Pack.
8. One image master is generated and reused for all channel variants. When the
   image API is unavailable, a PTIA template is used and the dashboard shows a
   warning.
9. Quality gates validate source attribution, semantic consistency, encoding,
   unsupported numbers, required channels and image presence.
10. Successful packages stop at `needs_final_review`, shown as `A Rever`.
11. The editor can submit the package to `Final OK` or reject it and request an
    alternative story.

## Queue safety

The daily run fills the queue up to six topics. The editor normally approves
four for `Final OK`; the remaining topics stay in `A Rever` and can be used the
next day. The next run only tops the queue back up to six. A rejected topic is
replaced explicitly, without being blocked by the remaining queue.

## Required GitHub Actions secrets

- `GEMINI_API_KEY`
- `PTIA_STATE_TOKEN`

Optional for generated editorial photography:

- `OPENAI_API_KEY`

Without `OPENAI_API_KEY`, the workflow remains functional and uses the branded
template fallback.

## Commands

Prepare or fill the local queue:

```powershell
python -m ptia_engine.cli editorial-auto --limit 6
```

Use only signals already verified:

```powershell
python -m ptia_engine.cli editorial-auto --limit 6 --no-scout
```

Import a LinkedIn page analytics export:

```powershell
python -m ptia_engine.cli linkedin-insights `
  --export "C:\path\linkedin-export.xls"
```

Rebuild conservative learning weights:

```powershell
python -m ptia_engine.cli learn --min-samples 5
```

The LinkedIn export is not fetched automatically because LinkedIn does not expose
this Premium page export through the current integration. Importing a new export
is idempotent: existing performance rows are updated instead of duplicated.
