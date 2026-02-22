# Dummy API

## Environment Variables

- `DATABASE_URL`: database connection string used by SQLAlchemy.
- `ADMIN_API_KEY`: shared bearer token for admin-only endpoints.
- `STRIPE_SECRET_KEY`: Stripe API secret key.
- `STRIPE_WEBHOOK_SECRET`: Stripe webhook endpoint secret used for signature validation.
- `STRIPE_PRICE_BASE_MONTHLY_ID`: Stripe price ID for fixed monthly subscription charge.
- `STRIPE_PRICE_METERED_ID`: Stripe price ID for metered usage charge.
- `STRIPE_SUCCESS_URL`: redirect URL after successful Stripe checkout.
- `STRIPE_CANCEL_URL`: redirect URL if Stripe checkout is canceled.

## Admin/Billing Authentication

All routes under `/admin/*` and `/billing/*` require:

- Header: `Authorization: Bearer <ADMIN_API_KEY>`

If the header is missing, malformed, invalid, or `ADMIN_API_KEY` is not configured, the API returns `401 Unauthorized`.

## Stripe Endpoints

- `POST /billing/stripe/checkout-session` (admin): create Stripe-hosted checkout session for a client.
- `POST /billing/stripe/portal-session` (admin): create Stripe customer portal session.
- `POST /billing/stripe/sync-usage` (admin): aggregate unsynced usage and report to Stripe metered billing.
- `POST /stripe/webhook` (public): receives Stripe webhook events with signature validation and idempotency.

## Migrations (Alembic)

1. Install dependencies:
   - `pip install -r requirements.txt`
2. Apply migrations:
   - `alembic upgrade head`
3. Create future migrations after model changes:
   - `alembic revision --autogenerate -m "your message"`
