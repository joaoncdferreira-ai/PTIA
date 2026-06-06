# PTIA Newsletter Cloud Automation

## Objective

Send the PTIA newsletter every Friday at 09:00 Europe/Lisbon without depending
on a PC or requiring a weekly manual action.

This phase does not change newsletter selection criteria, the dashboard UI,
Buffer schedules, Instagram automation or the LinkedIn comments engine.

## Production flow

1. The Render dashboard mirrors the current editorial JSONL state to Firestore.
2. Firebase runs `schedule_weekly_newsletter_cloud` every Friday at 08:45 in
   `Europe/Lisbon`.
3. The function compiles the edition from the latest shared state.
4. Brevo creates the campaign and schedules it for 09:00 using the ISO timestamp
   with the Lisbon UTC offset.
5. The provider campaign ID and status are written back to shared state.

The operation is idempotent:

- a campaign already marked `scheduled` or `sent` is never duplicated;
- a retry reuses an existing provider campaign ID;
- failed scheduled executions retry up to three times;
- concurrent state writes use SHA-256 version checks.

## Free-plan protection

Production is configured with `BREVO_MAX_RECIPIENTS=300`. Both local and cloud
preflight count the selected audience and stop before campaign scheduling when
the limit is exceeded. This avoids partial delivery under Brevo's free daily
allowance.

## Functions deployed

- `state_api`: authenticated shared-state API
- `newsletter_preflight`: compilation, Brevo list, sender and capacity checks
- `newsletter_subscribe`: public double opt-in endpoint used by the unchanged
  PTIA homepage signup flow
- `schedule_weekly_newsletter_cloud`: Friday scheduler

Instagram and site analytics functions remain excluded from this deployment.

## One-time requirements

### Firebase

1. Upgrade `ptia-content-engine-prod` to Blaze:
   https://console.firebase.google.com/project/ptia-content-engine-prod/usage/details
2. Run `firebase login --reauth`.

### Brevo

1. Create or use a free Brevo account.
2. Add and authenticate the PTIA sending domain, or verify the sender email.
3. Import or connect the PTIA subscriber list.
4. Create an API key.

The activator lists the available lists and senders. It then creates and
immediately deletes one validation draft, proving that the key, audience,
sender and current PTIA HTML are accepted without sending email.

### Render

Create an API key in Render Account Settings. The service ID is discovered
automatically from the existing `ptia-dashboard` service.

## Activation

```powershell
powershell.exe -ExecutionPolicy Bypass -File scripts\activate_newsletter_production.ps1
```

The script:

1. requests missing Brevo and Render credentials without printing them;
2. stores them only in Git-ignored `.env.local`;
3. generates a dedicated state token;
4. runs the complete test suite;
5. validates JSONL and seed files;
6. validates the Brevo account, list, sender and 300-recipient ceiling;
7. creates and deletes a Brevo validation draft;
8. uploads `PTIA_STATE_TOKEN` and `PTIA_BREVO_CONFIG`;
9. deploys Firestore and the four newsletter functions;
10. validates the live state API and newsletter compilation;
11. configures the required Render environment variables;
12. waits for the Render deployment to become live;
13. confirms `/api/health` reports `cloud_state_enabled=true`.

## Final production proof

Activation is complete only when:

- `newsletter_preflight` returns `status=ready` and `provider=brevo`;
- the compiled issue contains at least one item;
- the configured Brevo list and active sender exist;
- the recipient count is at most 300;
- Render reports cloud state enabled;
- Firebase shows Friday 08:45 Europe/Lisbon scheduling;
- Brevo shows the campaign for Friday 09:00 Europe/Lisbon.

## Rollback

Set `PTIA_CLOUD_STATE_ENABLED=false` in Render and redeploy. Firestore remains a
recovery copy. Re-enable the Windows fallback only if cloud scheduling is
deliberately paused.
