# PTIA Resources Automation

## Objective

Update the PTIA Resources layer every Monday at 09:00 Europe/Lisbon without
requiring editorial intervention for normal, well-supported changes.

## Flow

1. Apply proposals previously approved in the dashboard.
2. Run four isolated Gemini research tasks. The entities task checks acquisition,
   insolvency, liquidation, closure and inactivity before ranking changes.
3. Separate grounded web research from schema generation. The structured pass
   can only use URLs returned by Google Search grounding.
4. Validate every proposal deterministically and transactionally.
5. Apply material entity status updates and bounded ranking changes automatically
   only when confidence is at least 92%, there are two independent grounded
   HTTPS sources, at least one reference source, and all validation rules pass.
6. Treat new or materially changed records as exceptional and hold them for
   editorial approval.
7. Rebuild the Resources pages, archive the weekly edition, commit and push.

Each research area produces at most three proposals per run. Both AI passes
receive the current UTC date so that old announcements are not presented as
future events.

## Safety Rules

- A material non-active entity status bypasses gradual movement and moves the
  record to the public archive with reason, date and sources.
- Tool rankings may not introduce unknown IDs.
- Automatic tool movements are limited to three places per component.
- People/company ordering changes are limited to two places and always held for editorial review.
- New records must satisfy the complete catalog schema.
- New entities without a verifiable official LinkedIn URL are held as explicit
  exceptions.
- New tool and prompt scores must be real values from 1 to 100; zero and
  malformed numeric placeholders are rejected without interrupting the run.
- Future-tense claims tied to a year that has already passed are flagged.
- New glossary terms are compared with existing terms and aliases to surface
  likely duplicates.
- Tool proposals must use a direct HTTPS product URL rather than a grounding
  redirect.
- Each proposal is applied to an isolated copy and promoted only after the
  complete catalog passes validation.
- A rejected proposal cannot be automatically applied in a later run unless
  its evidence or payload materially changes.
- A provider failure creates an alert and keeps the previous valid edition.
- Invalid generated data never replaces the public catalog.

## Dashboard

The `Recursos` tab synchronizes the canonical queue from GitHub, shows pending
exceptions, confidence, sources, validation issues, approve/reject actions and
recent runs. Decisions are committed directly to the GitHub queue. `Executar
agora` dispatches the production workflow instead of running a divergent local
copy.

The dashboard refreshes remote state at startup and every five minutes. The
two state files are explicitly tracked despite the repository's general JSONL
ignore rule:

- `data/knowledge_review.jsonl`
- `data/knowledge_runs.jsonl`

Local review actions require an authenticated GitHub CLI session (`gh auth
login`) or a `GH_TOKEN`/`GITHUB_TOKEN` with repository contents permission.

## Required Secret

The GitHub repository must contain the Actions secret `GEMINI_API_KEY`.
Without it, the edition still builds from PTIA signals, but external discovery
is skipped and an alert is created in the dashboard.
