# Findings and fixes

## 1. The dashboard never read the database (Client A: "numbers don't match")

**How I found it:** Beach House Alpha (prop-001) showed USD 1,000.00, but the seed data has 4 reservations totalling 2,250.00. The backend log printed `Database error for prop-001 (tenant: tenant-a): ...` on every request, and the code then returned a hard-coded mock table.

**Root cause:** three problems in a row, all hidden by a `try/except` that returned hard-coded mock numbers:
- `requirements.txt` installed `sqlalchemy` without its asyncio extra, so `greenlet` was missing and the async engine could not even be imported.
- `DatabasePool.initialize()` built its URL from `settings.supabase_db_*` fields that do not exist. Settings only define `database_url`.
- It also used `QueuePool` (not allowed with an async engine), and `get_session()` was `async`, so `async with db_pool.get_session()` could not work.

**Fix:** `sqlalchemy[asyncio]`, build the asyncpg URL from `database_url`, use the default async pool, make `get_session()` a normal method, and initialize the pool once. The mock fallback is removed. If the database fails, the API now returns 503 instead of made-up figures.

## 2. Revenue from another company (Client B: privacy)

**Root cause:** the Redis key was `revenue:{property_id}`. Property IDs are only unique per tenant: `prop-001` is Beach House Alpha for Sunset and Mountain Lodge Beta for Ocean. Whichever client loaded first filled the cache, and the other client saw those numbers for 5 minutes.

**Fix:** the key is now `revenue:{tenant_id}:{property_id}`. The dashboard also no longer falls back to a shared `default_tenant` when a user has no tenant (403 instead).

The property dropdown was a hard-coded list of every company's properties, so Sunset could see Ocean's property names. Added `GET /api/v1/dashboard/properties`, which returns only the logged-in client's properties, and the dropdown uses it.

## 3. Totals "slightly off by a few cents" (finance)

**Root cause:** amounts are stored as `NUMERIC(10,3)` (e.g. 333.333 + 333.333 + 333.334), but the total was converted to `float` and then rounded in the browser. Binary floats cannot represent these values exactly.

**Fix:** the sum stays a `Decimal` and is rounded once to cents with `ROUND_HALF_UP` on the server, before it is sent.

## 4. March totals and time zones

**Root cause:** `calculate_monthly_revenue` built month boundaries in UTC and ignored the tenant. Reservation `res-tz-1` checks in at 2024-02-29 23:30 UTC, which is 1 March 00:30 in Paris, so for Sunset it belongs to March, not February.

**Fix:** the monthly query compares `check_in_date AT TIME ZONE properties.timezone` with the month boundaries and filters by tenant. It is exposed as `GET /api/v1/dashboard/monthly?property_id=&month=&year=`.

## Results (seed data)

| Client | Property | Before | After |
|---|---|---|---|
| Sunset | prop-001 total | 1,000.00 (mock) | 2,250.00 (4 bookings) |
| Sunset | prop-001 March 2024 | n/a | 2,250.00 (February: 0.00) |
| Ocean | prop-001 | could show Sunset's cached total | 0.00 (no bookings) |
| Ocean | dropdown | all 5 companies' properties | only its own 3 |

## Not done
- The frontend `SecureAPI` keeps its own request cache and tenant ID in memory. I checked logout and login as the other client in the browser and saw no leak, but this cache should also be cleared on logout.
- No automated tests were added. I verified with the API (`curl` for both clients) and in the browser.
