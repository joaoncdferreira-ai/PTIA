# PTIA Weekly Newsletter Automation

## Legacy Firebase flow

Firebase runs `schedule_weekly_newsletter_cloud` every Friday at 08:45 in
`Europe/Lisbon`. The function compiles or reuses the issue for that Friday and
creates a Brevo campaign scheduled for 09:00.

The active production executor is GitHub Actions. See
`docs/NEWSLETTER_GITHUB_AUTOMATION.md`.

The process is idempotent:

- an already scheduled or sent campaign is never duplicated;
- a failed scheduling retry reuses the stored provider campaign ID;
- drafts from an older compiler version are regenerated;
- Friday recovery is allowed only before 18:00; later runs target the next
  Friday.

## Required configuration

The Brevo configuration is stored in the Firebase secret
`PTIA_BREVO_CONFIG`:

```env
BREVO_API_KEY=
BREVO_LIST_IDS=
BREVO_MAX_RECIPIENTS=300
PTIA_NEWSLETTER_FROM_EMAIL=
PTIA_NEWSLETTER_FROM_NAME=PTIA
PTIA_NEWSLETTER_REPLY_TO=
```

Operational requirements:

- the sender address must be active in Brevo;
- the target list must contain the intended subscribers;
- the free-plan gate blocks delivery above 300 recipients;
- Brevo supplies its required footer branding on the free plan;
- the Brevo account must contain the legally required sender identity.

The homepage keeps the same visible signup form. Its submit handler calls the
Firebase `newsletter_subscribe` endpoint, which starts Brevo's official double
opt-in flow. Abuse limits are stored as salted hashes; raw emails and IP
addresses are not written to Firestore.

## Commands

Compile locally without contacting Brevo:

```powershell
.\.venv\Scripts\python.exe scripts\auto_newsletter_scheduler.py
```

Perform the live Brevo operation:

```powershell
.\.venv\Scripts\python.exe scripts\auto_newsletter_scheduler.py --live
```

Activate the cloud stack:

```powershell
powershell.exe -ExecutionPolicy Bypass -File scripts\activate_newsletter_production.ps1
```

## Editorial safeguards

- Only LinkedIn comments with `status=commented` can enter the newsletter.
- At most three recent published debates are included.
- Draft comments are never used.
- Performance language is used only when the performance ledger contains
  measurable results.
- Every issue must contain editorial items, HTML, plain text, and the Brevo
  unsubscribe tag before any external request.

## Recovery

If campaign creation succeeds but scheduling fails, rerun the activation or
live scheduler. The stored provider campaign ID is reused. Do not delete the
newsletter issue before the retry.

For a dated GitHub Actions recovery, dispatch `PTIA Weekly Newsletter` with
`live=true` and an ISO-8601 `send_at`, for example
`2026-06-12T17:00:00+01:00`.
