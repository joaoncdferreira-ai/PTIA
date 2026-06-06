# PTIA Newsletter Cloud Automation

## Objective

Send the PTIA newsletter every Friday at 09:00 Europe/Lisbon without depending
on a PC or requiring a weekly manual action.

This phase does not change newsletter selection criteria, the dashboard UI,
Buffer schedules, Instagram automation or the LinkedIn comments engine.

## Production flow

1. The Render dashboard writes the current editorial JSONL state to Firestore.
2. Firebase runs `schedule_weekly_newsletter_cloud` every Friday at 08:45 in
   `Europe/Lisbon`.
3. The function compiles the edition from the latest shared state.
4. MailerLite receives the campaign and schedules delivery for 09:00 using the
   API timezone ID for `Europe/Lisbon`.
5. The resulting campaign ID and status are written back to shared state.

The operation is idempotent:

- a campaign already marked `scheduled` or `sent` is never duplicated;
- a retry reuses an existing MailerLite campaign ID;
- failed scheduled executions retry up to three times;
- concurrent state writes use SHA-256 version checks instead of overwriting
  newer editorial work.

## Functions deployed in this phase

- `state_api`: authenticated shared-state API
- `newsletter_preflight`: authenticated cloud compilation and MailerLite group
  validation
- `schedule_weekly_newsletter_cloud`: Friday scheduler

Instagram and site analytics functions are deliberately excluded from this
deployment.

## One-time requirements

### Firebase

1. Upgrade `ptia-content-engine-prod` to Blaze:
   https://console.firebase.google.com/project/ptia-content-engine-prod/usage/details
2. Run:

```powershell
firebase login --reauth
```

### MailerLite

The activation needs:

- an API token;
- the subscriber Group ID;
- a verified sender email;
- an Advanced plan, because the official API requires it for custom HTML
  campaign content.

The activator creates and immediately deletes one validation draft. This proves
that the token, group, sender and current PTIA HTML are accepted without
scheduling or sending an email.

### Render

Create an API key in Render Account Settings. The service ID is discovered
automatically from the existing `ptia-dashboard` service.

Official instructions:
https://render.com/docs/api

## Activation

The code must first be committed and pushed to the branch used by Render.

Then run:

```powershell
powershell.exe -ExecutionPolicy Bypass -File scripts\activate_newsletter_production.ps1
```

The script:

1. securely requests missing MailerLite and Render credentials;
2. stores them only in Git-ignored `.env.local`;
3. generates a dedicated state token;
4. runs the complete test suite;
5. validates all newsletter JSONL and seed files;
6. resolves the official MailerLite `Europe/Lisbon` timezone ID;
7. creates and deletes a MailerLite validation draft;
8. uploads only `PTIA_STATE_TOKEN` and `PTIA_MAILERLITE_CONFIG`;
9. deploys Firestore and the three newsletter functions;
10. validates the live state API and cloud newsletter compilation;
11. configures the four required Render environment variables;
12. waits for the Render deployment to become `live`;
13. confirms `/api/health` reports `cloud_state_enabled=true`.

No secret is committed or printed.

## Final production proof

Activation is complete only when all of these are true:

- `newsletter_preflight` returns `status=ready`;
- the compiled issue contains at least one item;
- the configured MailerLite group exists;
- the Render dashboard reports cloud state enabled;
- Firebase shows the Friday 08:45 Europe/Lisbon schedule;
- MailerLite schedules the campaign for Friday 09:00 Europe/Lisbon.

The old Windows task must only be disabled after the cloud checks pass. Keeping
both active before verification is safe because the newsletter ledger prevents
duplicates, but the PC task should not remain as the long-term runner.

## Rollback

Set `PTIA_CLOUD_STATE_ENABLED=false` in Render and redeploy. Firestore remains a
recovery copy. Re-enable the Windows task only if cloud scheduling is
deliberately paused.
