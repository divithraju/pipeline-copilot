# PipelineCopilot — product definition

**One line:** Describe a data pipeline in plain English. Get a validated spec, a safe sandbox run with a quality report, and production code (Python + Airflow DAG).

## Customer and problem
- **Users:** data engineers, analytics engineers, and analysts who wait on engineers.
- **Buyer:** head of data / engineering manager.
- **Problem:** routine transformations (dedupe, clean, aggregate) eat engineering time, and generic AI code assistants produce unreviewed code that nobody trusts in production.

## Differentiators
1. Spec-first: the AI outputs a reviewable spec, not arbitrary code.
2. Safe by construction: validated, compiled and sandboxed.
3. Quality report on every run.
4. Exports portable code (no lock-in).

## Pricing (suggested, validate with users)
| Plan | For | Includes |
|---|---|---|
| Free | Individuals | 50 runs / month, files ≤ 10 MB |
| Team | Data teams | Higher limits, shared spec library, scheduled runs |
| Enterprise | Regulated orgs | Self-hosted, SSO, audit log, private LLM endpoint |

## Metrics to track
Spec validity rate on first try · repair-retry rate · % runs with quality warnings · time from request to first successful run · exports per user.
