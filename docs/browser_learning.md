# Browser learning retries

Browser execution learning runs in a background worker using a persistent
SQLite queue. Each evidence chunk needs one reflection request; valid lessons
may need one additional curation request. These requests use the fast model.

HTTP 401/403 authentication or authorization failures pause the affected
execution (`status=paused`). Ordinary failures retry with exponential backoff,
up to three failed processing attempts in total, then retain the execution as
`status=failed`. Both states retain the execution and `last_error` for diagnosis
and remain stopped after a process restart. Correcting credentials does not
automatically restart paused executions. Cancellation releases the lease
without consuming the failure budget.

Learning requests disable nested SDK retries; the durable queue owns retries.
The three-attempt limit applies to processing attempts, rather than individual
HTTP requests: an execution with multiple evidence chunks can make multiple
requests in each attempt.

The worker polls every five seconds, but only drains when a record is eligible
now and no consumer holds a live database-wide lease. Backoff, paused records
and records already being processed do not trigger empty drains. Empty drain
messages use DEBUG; batches that process or fail records remain visible at INFO.