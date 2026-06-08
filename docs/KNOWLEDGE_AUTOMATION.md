# PTIA Resources Automation

## Objective

Update the PTIA Resources layer every Monday at 09:00 Europe/Lisbon without
requiring editorial intervention for normal, well-supported changes.

## Flow

1. Apply proposals previously approved in the dashboard.
2. Use Gemini with Google Search grounding to research people, companies,
   tools, prompts and glossary terms.
3. Validate every proposal deterministically.
4. Apply proposals automatically only when confidence is at least 92%, there
   are two independent HTTPS sources, and movement limits are respected.
5. Hold exceptional proposals in `data/knowledge_review.jsonl`.
6. Rebuild the Resources pages, archive the weekly edition, commit and push.

## Safety Rules

- Tool rankings may not introduce unknown IDs.
- Automatic tool movements are limited to three places per component.
- Automatic people/company movements are limited to two places.
- New records must satisfy the complete catalog schema.
- A provider failure creates an alert and keeps the previous valid edition.
- Invalid generated data never replaces the public catalog.

## Dashboard

The `Recursos` tab shows pending exceptions, confidence, sources, validation
issues, approve/reject actions, recent runs and a manual `Executar agora`
action. Approved proposals are applied on the next run or immediately when a
manual run is requested.

## Required Secret

The GitHub repository must contain the Actions secret `GEMINI_API_KEY`.
Without it, the edition still builds from PTIA signals, but external discovery
is skipped and an alert is created in the dashboard.
