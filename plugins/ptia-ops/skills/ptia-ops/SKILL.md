---
name: ptia-ops
description: "Use for PTIA operational checks: validating scheduled posts, checking copy/image issues, confirming site-feed timing, and updating one Buffer post from local validated PTIA data."
metadata:
  short-description: PTIA validation and Buffer ops
---

# PTIA Ops

Use the `ptia-ops` MCP tools before any PTIA publishing action.

Recommended sequence:

1. `validate_schedule(date, future_only=true)`
2. `audit_buffer_against_local(date, future_only=true)` when posts are already scheduled in Buffer
3. If any failure exists, inspect with `get_final_post(post_id)` and `get_buffer_post(buffer_post_id)`
4. Fix locally in `C:\Users\joaon\ptia-content-engine`
5. Re-run `validate_schedule` and `compare_local_post_to_buffer(post_id)`
6. For a single scheduled Buffer correction, use `update_buffer_post_from_local(post_id)`
7. Check `validate_site_feed_no_future()` before deploying or publishing the site feed
8. Check `check_public_site_status()` after deploys
9. Check `check_ptia_dns_basics()` after DNS/newsletter changes
10. Use `import_instagram_performance(limit)` only after `META_ACCESS_TOKEN` and `META_INSTAGRAM_BUSINESS_ID` are configured

Rules:

- Do not update Buffer when `copy_issues` is not empty.
- Do not assume local data matches Buffer; use `audit_buffer_against_local`.
- Do not update unrelated channels.
- Treat returned Buffer `due_at` as UTC.
- X remains disabled until the PTIA account suspension is resolved.
- DNS tools are read-only checks. Do not change Cloudflare records from this plugin.
- Instagram metrics use the official Meta Graph API and write to `data/content_performance.jsonl`.
