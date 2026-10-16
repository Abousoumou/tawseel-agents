import os

def env(key, default=""):
    return os.getenv(key) or default

BASE_URL = env("TAWSEEL_BASE_URL", "https://delivery-for-less.vercel.app")
HEADLESS = env("HEADLESS", "1") == "1"
MODEL = env("AGENT_MODEL", "gpt-4o-mini")
MAX_STEPS = int(env("AGENT_MAX_STEPS", "25"))
ARTIFACT_DIR = env("ARTIFACT_DIR", "artifacts")
POD_FILE = env("POD_FILE", "fixtures/pod.png")

class Creds:
    def __init__(self, role):
        self.email = env(f"TAWSEEL_{role.upper()}_EMAIL")
        self.password = env(f"TAWSEEL_{role.upper()}_PASSWORD")

    @property
    def ok(self):
        return bool(self.email and self.password)

    def __repr__(self):
        return f"<Creds {self.email or 'MISSING'}>"
