# Deployment notes

Checked November 11, 2026. No public deployment or paid services were created.

## What this app needs

A Python process for FastAPI and the daily scheduler, a persistent SQLite file,
and a React build served either separately or through the backend. Provider
keys belong in the hosting service's server-side secrets. Preserve the database
across deployments so story links, history, and daily collection claims survive.
The current server expects its database at artifacts/courtside.db.

## Hosting findings

[Render Free](https://render.com/docs/free) sleeps after 15 minutes without
traffic and loses local filesystem changes on restart, redeploy, or spin-down.
It cannot attach a persistent disk. It is therefore unsuitable for this app's
current SQLite history and in-process schedule without architecture changes.
Render's free Postgres also expires after 30 days.

[Oracle Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
include compute and block storage. A suitable available VM could run the current
Python process with SQLite on persistent storage, making it a free candidate to
investigate. Availability and account eligibility must be checked before choosing
it. Oracle may reclaim idle compute. This path also requires configuring Linux,
HTTPS, process restarts, and database backups. Do not select paid resources or
upgrade an account without approval.

A managed Python service with a paid persistent disk is another path if a small
hosting budget is later approved. No paid plan has been selected.

## Source use

[GNews terms](https://gnews.io/legal/terms-of-service) limit unpaid access to
personal, academic, evaluation, and other non-commercial uses. Do not assume
that a public or resume-related deployment is automatically covered. Confirm
how the intended demo fits those terms before enabling it publicly. Retain source
attribution and review the data-use conditions separately from request quotas.

[FreeNewsApi.ai terms](https://freenewsapi.ai/legal/terms) allow storing and
processing API data and commercial API use within plan limits. They require
linking to original articles and do not license publisher text. Keep the existing
headline-only handling for this source. Its API permission is not blanket
permission to reproduce full publisher articles.

RSS discovery also does not imply permission to reproduce article text. Review
the enabled publisher's feed-use conditions before public deployment. This
research does not certify every source or publisher for public use.

## Next implementation step

Choose the hosting path before adding provider-specific deployment files. For a
free deployment retaining SQLite, first verify access to a suitable VM. Then
prepare the React build, HTTPS routing, process management, persistent database
location, and backups. Test collection and shared-story links after a restart.
Do not publish a site until the user approves the concrete deployment.
