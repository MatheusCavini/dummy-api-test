# Dummy API

## Environment Variables

- `DATABASE_URL`: database connection string used by SQLAlchemy.
- `ADMIN_API_KEY`: shared bearer token for admin-only endpoints.

## Admin/Billing Authentication

All routes under `/admin/*` and `/billing/*` require:

- Header: `Authorization: Bearer <ADMIN_API_KEY>`

If the header is missing, malformed, invalid, or `ADMIN_API_KEY` is not configured, the API returns `401 Unauthorized`.
