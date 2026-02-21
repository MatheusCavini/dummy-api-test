import os

ENVIRONMENT = os.getenv("ENVIRONMENT", "sandbox")

class Settings:
    def __init__(self):
        self.environment = ENVIRONMENT

settings = Settings()
