import os


ENVIRONMENT = os.getenv("ENVIRONMENT", "sandbox")


class Settings:
    def __init__(self):
        self.environment = ENVIRONMENT
        self.stripe_secret_key = os.getenv("STRIPE_SECRET_KEY")
        self.stripe_webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
        self.stripe_price_base_monthly_id = os.getenv("STRIPE_PRICE_BASE_MONTHLY_ID")
        self.stripe_price_metered_id = os.getenv("STRIPE_PRICE_METERED_ID")
        self.stripe_success_url = os.getenv("STRIPE_SUCCESS_URL")
        self.stripe_cancel_url = os.getenv("STRIPE_CANCEL_URL")


settings = Settings()
