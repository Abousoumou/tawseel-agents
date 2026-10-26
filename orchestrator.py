import json
import os
import sys
from datetime import datetime
from playwright.sync_api import sync_playwright

from config import BASE_URL, HEADLESS, ARTIFACT_DIR, POD_FILE, MAX_STEPS, Creds
from browser import BrowserSession
from roles import build_agents

os.makedirs(ARTIFACT_DIR, exist_ok=True)

CONTEXT = {
    "base_url": BASE_URL,
    "pod_file": POD_FILE,
    "order": {
        "pickup_address": "Marina Mall, Dubai Marina, Dubai, UAE",
        "pickup_contact": "QA Sender",
        "pickup_phone": "+971500000001",
        "dropoff_address": "Cluster D, Jumeirah Lakes Towers, Dubai, UAE",
        "dropoff_contact": "QA Recipient",
        "dropoff_phone": "+971500000002",
        "package": "Small box, approx 2 kg, handle with care",
        "vehicle_preference": "Scooter",
        "notes": "AUTOMATED QA TEST ORDER - safe to cancel",
    },
    "known_facts": {},
}

LOG = []


def phase(title):
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}", flush=True)


def record(name, res):
    entry = {
        "agent": name,
        "status": res.get("status"),
        "summary": res.get("summary") or res.get("reason", ""),
        "result": res.get("result", {}),
        "steps": res.get("steps"),
    }
    LOG.append(entry)
    print(f"[{name}] {entry['status']} — {entry['summary'][:300]}", flush=True)
    return entry


def main():
    creds = {r: Creds(r) for r in ["sender", "courier", "admin"]}
    missing = [r for r, c in creds.items() if not c.ok]
    if missing:
        print(f"FATAL: missing credentials for roles: {missing}", flush=True)
        sys.exit(1)

    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, args=["--no-sandbox"])
        sessions = {
            r: BrowserSession(r, browser)
            for r in ["sender", "courier", "admin", "evaluator"]
        }
        agents = build_agents(sessions, creds)

        for s in sessions.values():
            s.goto(BASE_URL)

        # ---- Phase 1: log everyone in -------------------------------------
        phase("PHASE 1 — Authentication")
        for role in ["sender", "courier", "admin"]:
            res = agents[role].run_task(
                f"Log in to TAWSEEL as the {role}. Use the credentials provided. "
                f"If there is no account and sign-up is available, create one. "
                f"Stop with 'done' once you can see your role's dashboard.",
                CONTEXT,
                max_steps=22,
            )
            results[f"login_{role}"] = record(role, res)
            if res["status"] != "done":
                print(f"Login failed for {role} — aborting run.", flush=True)
                CONTEXT["known_facts"]["blocked_at"] = f"login_{role}"
                break

        # ---- Phase 2: sender creates order --------------------------------
        if "blocked_at" not in CONTEXT["known_facts"]:
            phase("PHASE 2 — Sender creates a delivery order")
            res = agents["sender"].run_task(
                "Create a new delivery order using the details in SHARED CONTEXT -> order. "
                "Fill every required field. If the app asks for a vehicle type, use the "
                "vehicle_preference. Submit the order. "
                "In 'result', return the order id / reference number, the quoted price, and "
                "the order status you see on screen.",
                CONTEXT,
                max_steps=MAX_STEPS,
            )
            results["create_order"] = record("sender", res)
            if res.get("result"):
                CONTEXT["known_facts"]["order"] = res["result"]
            if res["status"] != "done":
                CONTEXT["known_facts"]["blocked_at"] = "create_order"

        # ---- Phase 3: courier bids ----------------------------------------
        if "blocked_at" not in CONTEXT["known_facts"]:
            phase("PHASE 3 — Courier finds the order and submits a bid")
            res = agents["courier"].run_task(
                "Open the list of available delivery orders. Find the QA test order that was "
                "just created (see SHARED CONTEXT -> order and known_facts -> order). "
                "Open it and submit a bid: a reasonable price, a short ETA, and the scooter "
                "vehicle type. In 'result', report the order id and the bid you submitted.",
                CONTEXT,
                max_steps=MAX_STEPS,
            )
            results["courier_bid"] = record("courier", res)
            if res.get("result"):
                CONTEXT["known_facts"]["bid"] = res["result"]
            if res["status"] != "done":
                CONTEXT["known_facts"]["blocked_at"] = "courier_bid"

        # ---- Phase 4: sender accepts the bid -------------------------------
        if "blocked_at" not in CONTEXT["known_facts"]:
            phase("PHASE 4 — Sender reviews and accepts the bid")
            res = agents["sender"].run_task(
                "Open your orders. Find the QA test order. Open the bids / offers section. "
                "Review the bid from the delivery agent and accept it. "
                "In 'result', report the accepted price, the delivery agent name, and the ETA.",
                CONTEXT,
                max_steps=MAX_STEPS,
            )
            results["accept_bid"] = record("sender", res)
            if res.get("result"):
                CONTEXT["known_facts"]["accepted"] = res["result"]
            if res["status"] != "done":
                CONTEXT["known_facts"]["blocked_at"] = "accept_bid"

        # ---- Phase 5: courier executes the delivery ------------------------
        if "blocked_at" not in CONTEXT["known_facts"]:
            phase("PHASE 5 — Courier performs the delivery")
            res = agents["courier"].run_task(
                "You have been assigned the QA test order. Complete the delivery: "
                "mark the order as picked up, then in transit, then delivered. "
                "When the app asks for proof of delivery, upload the image at the path given "
                "in SHARED CONTEXT -> pod_file (use 'upload' on a visible file input, or "
                "'upload_any' if you cannot find one). "
                "In 'result', report the final order status and your earnings shown for this order.",
                CONTEXT,
                max_steps=MAX_STEPS,
            )
            results["delivery"] = record("courier", res)
            if res.get("result"):
                CONTEXT["known_facts"]["delivery"] = res["result"]
            if res["status"] != "done":
                CONTEXT["known_facts"]["blocked_at"] = "delivery"

        # ---- Phase 6: sender confirms --------------------------------------
        if "blocked_at" not in CONTEXT["known_facts"]:
            phase("PHASE 6 — Sender confirms delivery and rates")
            res = agents["sender"].run_task(
                "Open your QA test order. Confirm that the package was received. "
                "Rate the delivery agent. "
                "In 'result', report the final order status and the amount you were charged.",
                CONTEXT,
                max_steps=MAX_STEPS,
            )
            results["confirm"] = record("sender", res)
            if res.get("result"):
                CONTEXT["known_facts"]["confirmed"] = res["result"]

        # ---- Phase 7: independent evaluation -------------------------------
        phase("PHASE 7 — Evaluator verifies the outcome")
        checks = (
            "1. The QA test order exists and its final status is Delivered.\n"
            "2. The delivery agent has a proof-of-delivery image attached.\n"
            "3. The platform fee is exactly 12% of the order subtotal.\n"
            "4. The delivery agent's earnings for this order equal subtotal minus 12%.\n"
            "5. The order appears in the admin orders list with the correct assigned agent.\n"
            "6. The admin revenue / platform-fee total includes this order.\n"
            "7. No error messages, blank screens, or broken states are visible."
        )
        res = agents["evaluator"].run_task(
            "Log in as admin. Navigate the dashboard to verify these checks against the "
            "QA test order described in SHARED CONTEXT. Return the structured result object "
            "described in your instructions.\n\n" + checks,
            CONTEXT,
            max_steps=MAX_STEPS,
        )
        results["evaluation"] = record("evaluator", res)

        # ---- screenshots of final state ------------------------------------
        for name, s in sessions.items():
            try:
                s.shot()
            except Exception:
                pass
            s.close()

        browser.close()

    # ---- report -----------------------------------------------------------
    with open(os.path.join(ARTIFACT_DIR, "results.json"), "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    ev = results.get("evaluation", {}).get("result", {}) or {}
    overall = ev.get("overall", "NOT EVALUATED")

    lines = [
        "# TAWSEEL Agent Test Report",
        "",
        f"**When:** {datetime.utcnow().isoformat()}Z  ",
        f"**Target:** {BASE_URL}  ",
        f"**Overall:** `{overall}`",
        "",
        "## Phase results",
        "",
        "| Phase | Status | Detail |",
        "|---|---|---|",
    ]
    for e in LOG:
        detail = str(e["summary"]).replace("|", "/")[:220]
        lines.append(f"| {e['agent']} / {e['status']} | `{e['status']}` | {detail} |")

    if ev.get("checks"):
        lines += ["", "## Verification checks", "", "| Check | Result | Evidence |", "|---|---|---|"]
        for c in ev["checks"]:
            mark = "PASS" if c.get("pass") else "FAIL"
            ev_txt = str(c.get("evidence", "")).replace("|", "/")[:220]
            lines.append(f"| {c.get('name')} | `{mark}` | {ev_txt} |")

    if ev.get("bugs"):
        lines += ["", "## Suspected bugs", ""]
        lines += [f"- {b}" for b in ev["bugs"]]

    lines += ["", "## Shared context at end of run", "", "```json",
              json.dumps(CONTEXT, indent=2, ensure_ascii=False), "```", ""]

    report = "\n".join(lines)

    with open(os.path.join(ARTIFACT_DIR, "report.md"), "w") as f:
        f.write(report)

    step_summary = os.getenv("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a") as f:
            f.write(report)

    print(report)


if __name__ == "__main__":
    main()
