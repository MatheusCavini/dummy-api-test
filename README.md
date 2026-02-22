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
- `CORS_ALLOW_ORIGINS`: comma-separated allowed origins for browser clients (default `*`).
- `CORS_ALLOW_ORIGIN_REGEX`: regex for allowed origins (default allows any `localhost`/`127.0.0.1` port).

## Admin/Billing Authentication

All routes under `/admin/*` and `/billing/*` require:

- Header: `Authorization: Bearer <ADMIN_API_KEY>`

If the header is missing, malformed, invalid, or `ADMIN_API_KEY` is not configured, the API returns `401 Unauthorized`.

## Stripe Endpoints

- `POST /billing/stripe/checkout-session` (admin): create Stripe-hosted checkout session for a client.
- `POST /billing/stripe/portal-session` (admin): create Stripe customer portal session.
- `POST /billing/stripe/sync-usage` (admin): aggregate unsynced usage and report to Stripe metered billing.
- `POST /stripe/webhook` (public): receives Stripe webhook events with signature validation and idempotency.

## Client self-service authentication

- `CLIENT_JWT_SECRET`, `CLIENT_JWT_ALGORITHM`, `CLIENT_JWT_EXP_SECONDS`, `CLIENT_SESSION_TTL_SECONDS`, and `CLIENT_PENDING_API_KEY_TTL_SECONDS` control the JWT signing, expiration, and temporary delivery windows.
- `CLIENT_DEFAULT_SERVICE_CODE` must point to an active `services.code` so we can auto-issue an API key after a completed Stripe checkout.
- The landing page uses:
  - `POST /clients/register` to create a client record, hash their password, create a Stripe customer, and send back a checkout session URL.
  - `POST /clients/login` to verify credentials, issue a JWT, and receive any pending API key reserved by the webhook.
  - `POST /clients/logout` to invalidate the current JWT session.
  - `GET /clients/me` to view the authenticated profile.
  - `GET /clients/pricing-plans` to list selectable fixed plans: `standard` (base monthly only) and `metered` (base monthly + metered usage).
  - `POST /clients/checkout-session` to create a Stripe checkout session using `{ "plan_code": "standard" | "metered" }`.
  - `GET /clients/me/api-keys` to list issued API keys and consume the raw key stored temporarily after Stripe checkout completes.

## Landing Page Redirects

- Configure:
  - `STRIPE_SUCCESS_URL` with a landing URL such as `http://localhost:8080/index.html?step=api-key`.
  - `STRIPE_CANCEL_URL` with a landing URL such as `http://localhost:8080/index.html?step=cancel`.
- The static test page lives in `landing-page/` and can be served with `npx http-server landing-page -p 8080`.

## Migrations (Alembic)

1. Install dependencies:
   - `pip install -r requirements.txt`
2. Apply migrations:
   - `alembic upgrade head`
3. Create future migrations after model changes:
   - `alembic revision --autogenerate -m "your message"`
