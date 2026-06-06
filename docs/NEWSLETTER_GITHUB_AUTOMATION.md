# PTIA Newsletter Automation Without Firebase

## Active design

GitHub Actions is the weekly executor. Brevo remains the delivery provider.
Firebase Blaze, Firestore and Render secrets are not required.

The workflow `.github/workflows/weekly-newsletter.yml` runs at both possible
UTC equivalents of 08:35 Europe/Lisbon. A timezone guard permits execution only
on Friday during the 08:00-10:59 Lisbon recovery window.

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
- With zero recipients, compilation is validated but no campaign is created.
- More than 300 recipients is blocked while the free-plan ceiling is active.
- Manual workflow runs are dry-run by default.
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

Without Firebase, public signup should use a native Brevo full-page/embedded
form with double confirmation, GDPR fields and CAPTCHA. Brevo provides iframe,
HTML and simple HTML embed code from Contacts > Forms > Sign-up.

The existing site form must only be switched after the Brevo form is published
and its embed code is available. This is separate from weekly delivery.
