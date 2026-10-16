import json
import os
from playwright.sync_api import sync_playwright

from config import BASE_URL, HEADLESS, ARTIFACT_DIR
from browser import BrowserSession
from config import Creds

os.makedirs(ARTIFACT_DIR, exist_ok=True)

ROLES = ["sender", "courier", "admin"]
summary = {}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=HEADLESS, args=["--no-sandbox"])

    for role in ROLES:
        creds = Creds(role)
        s = BrowserSession(f"recon-{role}", browser)

        entry = {"email": creds.email or "MISSING", "steps": []}
        try:
            s.goto(BASE_URL)
            snap = s.snapshot()
            s.shot()
            entry["landing"] = {"url": snap["url"], "title": snap["title"],
                                "elements": len(snap["elements"])}

            if not creds.ok:
                entry["status"] = "no credentials configured"
                summary[role] = entry
                continue

            from llm import decide
            from agent import Agent
            from roles import SENDER_PERSONA, COURIER_PERSONA, ADMIN_PERSONA

            personas = {"sender": SENDER_PERSONA, "courier": COURIER_PERSONA,
                        "admin": ADMIN_PERSONA}
            a = Agent(role, role, s, creds, personas[role])

            res = a.run_task(
                "Log in to TAWSEEL with your credentials, then navigate to your main "
                "dashboard. Stop with 'done' once you can see your dashboard, and in "
                "'result' describe every navigation item and button you can see.",
                {"base_url": BASE_URL},
                max_steps=12,
            )
            entry["login_result"] = {k: v for k, v in res.items() if k != "history"}
            entry["trace"] = res.get("history", [])

            dash = s.snapshot()
            s.shot()
            entry["dashboard"] = {"url": dash["url"], "title": dash["title"],
                                  "elements": dash["elements"][:80],
                                  "bodyText": dash["bodyText"]}

        except Exception as e:
            entry["error"] = f"{type(e).__name__}: {e}"
        finally:
            s.close()

        summary[role] = entry

    browser.close()

with open(os.path.join(ARTIFACT_DIR, "recon.json"), "w") as f:
    json.dump(summary, f, indent=2)

print(json.dumps(summary, indent=2)[:8000])
