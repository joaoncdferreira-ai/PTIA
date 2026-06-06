# Newsletter

The production runbook is in
[`NEWSLETTER_CLOUD_AUTOMATION.md`](NEWSLETTER_CLOUD_AUTOMATION.md).

The cloud design uses Firestore for shared editorial state, Firebase for the
Friday scheduler and MailerLite for delivery. The Windows task remains only as
a temporary fallback until the cloud preflight is complete.
