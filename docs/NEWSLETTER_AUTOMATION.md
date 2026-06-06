# PTIA Weekly Newsletter Automation

## Production flow

The Windows task `PTIA_Weekly_Newsletter` runs every Friday at 08:45 in the
machine's Europe/Lisbon local time. It executes:

```powershell
scripts\run_newsletter_task.ps1
```

The wrapper uses the project virtual environment, writes an audit log to
`data/newsletter_scheduler.log`, and calls the scheduler with `--live`. The
scheduler compiles or reuses one issue for the target Friday and schedules it
in MailerLite for 09:00. The task runs under the current Windows user with
`StartWhenAvailable`; the user session may be locked, but the machine must be
powered on and the user must have logged in.

The process is idempotent:

- an already scheduled or sent campaign is never duplicated, including with
  `--force`;
- a failed schedule retry reuses the stored MailerLite campaign ID;
- drafts from an older compiler version are regenerated;
- Friday recovery is allowed only before 18:00; later runs target the next
  Friday.

## Required configuration

Add these values to `.env.local`:

```env
MAILERLITE_API_KEY=
MAILERLITE_GROUP_ID=
PTIA_NEWSLETTER_FROM_EMAIL=
PTIA_NEWSLETTER_FROM_NAME=PTIA
PTIA_NEWSLETTER_REPLY_TO=
```

`MAILERLITE_GROUP_IDS=123,456` can replace the single group setting.

Optional MailerLite IDs must be integers:

```env
MAILERLITE_TIMEZONE_ID=
MAILERLITE_LANGUAGE_ID=
```

Omit `MAILERLITE_TIMEZONE_ID` to use the account timezone. Do not use a
timezone name or an unverified numeric ID.

Operational requirements:

- the sender address must be verified in MailerLite;
- the target group must be the intended subscriber audience;
- the MailerLite plan must support custom HTML campaign content through the
  API;
- the MailerLite account profile must contain the legally required sender
  identity and postal address.

## Commands

Compile locally without contacting MailerLite:

```powershell
.\.venv\Scripts\python.exe scripts\auto_newsletter_scheduler.py
```

Perform the live MailerLite operation:

```powershell
.\.venv\Scripts\python.exe scripts\auto_newsletter_scheduler.py --live
```

Register or update the weekly Windows task:

```powershell
powershell.exe -ExecutionPolicy Bypass -File scripts\register_newsletter_task.ps1
```

## Editorial safeguards

- Only LinkedIn comments with `status=commented` can enter the newsletter.
- At most three recent published debates are included.
- Draft comments are never used.
- Performance language is used only when the performance ledger contains
  measurable results. Otherwise the issue is labelled as editorial curation.
- Every issue must contain editorial items, HTML, plain text, and the
  MailerLite unsubscribe tag before any external request.

## Cloud transition

The shared Firestore state and cloud scheduler are implemented but remain
disabled until Firebase billing, production secrets and the migration preflight
are complete. Until then, the Windows task remains the active runner.

Do not run the Windows and cloud Friday schedules independently. Disable the
Windows task only after the cloud function and shared state have been verified.
See `docs/NEWSLETTER_CLOUD_AUTOMATION.md`.

## Recovery

Inspect:

```powershell
Get-Content data\newsletter_scheduler.log -Tail 100
Get-ScheduledTask -TaskName PTIA_Weekly_Newsletter
```

If a campaign creation succeeded but scheduling failed, rerun with `--live`.
The stored campaign ID is reused. Do not delete the local issue before the
retry.
