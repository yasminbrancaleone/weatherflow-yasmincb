# ADR 0003: Alert channel and deduplication

- Status: Accepted
- Date: 2026-11-25

## Context

The project needs actionable alerts for high-risk weather and exhausted Airflow
task retries. No external alert channel or webhook was configured for this
learning project.

## Decision

Use the warehouse `alerts` table and application logs as the fallback channel.
Record each alert key in `alerts_sent` in the same transaction as its message.
Risk keys use the city and UTC start of a contiguous risk period; failure keys
use the DAG, task, and Airflow run ID. Risk messages include the city, UK-local
hours, and detected wind, rain, snow, or storm reasons. Failure messages include
the DAG, task, and try number.

## Consequences

Repeated checks do not record the same risk period or failed task run twice.
The database and log provide an audit trail without adding a webhook secret. If
the warehouse is unavailable, the failure callback logs that persistence failed
and propagates the error; a database-backed alert cannot be guaranteed then.

## Alternatives considered

- Slack, Discord, or Teams incoming webhook: deferred because no channel URL was
  configured and a secret must not be committed.
- Send an email: deferred because SMTP credentials and delivery configuration
  are not available.
- Log every alert without a database key: rejected because reruns could create
  repeated messages with no deduplication record.
