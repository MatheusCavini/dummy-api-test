import os

from dotenv import load_dotenv


load_dotenv()

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
        self.client_jwt_secret = os.getenv("CLIENT_JWT_SECRET")
        self.client_jwt_algorithm = os.getenv("CLIENT_JWT_ALGORITHM", "HS256")
        self.client_jwt_exp_seconds = self._get_int_env("CLIENT_JWT_EXP_SECONDS", 3600)
        self.client_session_ttl_seconds = self._get_int_env(
            "CLIENT_SESSION_TTL_SECONDS", self.client_jwt_exp_seconds
        )
        self.client_pending_api_key_ttl_seconds = self._get_int_env(
            "CLIENT_PENDING_API_KEY_TTL_SECONDS", 600
        )
        self.client_default_service_code = os.getenv("CLIENT_DEFAULT_SERVICE_CODE")
        self.cors_allow_origins = self._get_list_env("CORS_ALLOW_ORIGINS", ["*"])
        self.cors_allow_origin_regex = os.getenv(
            "CORS_ALLOW_ORIGIN_REGEX",
            r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        )

    @staticmethod
    def _get_int_env(name: str, default: int) -> int:
        raw = os.getenv(name)
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    @staticmethod
    def _get_list_env(name: str, default: list[str]) -> list[str]:
        raw = os.getenv(name)
        if not raw:
            return default
        parts = [part.strip() for part in raw.split(",")]
        values = [part for part in parts if part]
        return values or default


settings = Settings()
