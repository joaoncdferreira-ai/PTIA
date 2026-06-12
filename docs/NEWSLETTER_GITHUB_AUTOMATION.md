# PTIA Newsletter Automation Without Firebase

## Active design

GitHub Actions is the weekly executor. Brevo remains the delivery provider.
Firebase Blaze, Firestore and Render secrets are not required.

The workflow `.github/workflows/weekly-newsletter.yml` prepares each edition on
Thursday evening and runs an idempotent recovery early on Friday. Both runs
target Friday at 09:00 Europe/Lisbon. Preparing the Brevo campaign in advance
avoids depending on GitHub Actions starting at an exact minute.

## Data source

The newsletter compiles from `data/final_posts.jsonl`, which is versioned and
updated by the existing publication flow. Optional ledgers are created as empty
runner files when absent. Selection remains limited to recent posts with
`scheduled` or `published` status.

## Safety properties

- Brevo is queried for an exact `PTIA Weekly - YYYY-MM-DD` campaign before any
  campaign is created.
- Existing queued, scheduled or sent campaigns are never duplicated.
- Existing drafts are reused.
- Campaign names are derived from the Friday delivery date, even when the
  campaign is created on Thursday.
- The free-plan campaign payload does not request Brevo's paid tag feature.
- With zero recipients, compilation is validated but no campaign is created.
- More than 300 recipients is blocked while the free-plan ceiling is active.
- Manual workflow runs are dry-run by default.
- Manual live recovery accepts an optional ISO-8601 `send_at` value.
- The workflow has read-only repository permissions.

## Required GitHub secrets

- `BREVO_API_KEY`
- `BREVO_LIST_IDS`
- `PTIA_NEWSLETTER_FROM_EMAIL`
- `PTIA_NEWSLETTER_REPLY_TO`

## One-time activation

```powershell
powershell.exe -ExecutionPolicy Bypass -File scripts\activate_newsletter_github.ps1
```

The activator validates the Brevo account and local compilation, uploads the
four repository secrets and waits for a successful GitHub Actions preflight.
Secrets are never printed or committed.

## Free Brevo signup form

The production homepage posts directly to the native Brevo form
`PTIA Weekly - Site`. The form:

- targets list `PTIA Weekly`;
- uses double opt-in with template `PTIA Weekly - Double opt-in`;
- preserves the existing PTIA card and interaction;
- exposes no API key in the browser;
- requires no Firebase or Vercel function.

MailerLite is no longer loaded by the homepage.

## Production status

- GitHub secrets configured.
- Brevo sender `info@ptia.pt` active with DKIM and DMARC.
- Controlled live workflow passed with zero recipients and created no campaign.
- Native signup form published and connected to the weekly list.
- Automatic delivery target: Friday at 09:00 Europe/Lisbon.
