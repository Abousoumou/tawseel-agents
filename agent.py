import json
from llm import decide

ACTION_DOC = """
Reply with ONE JSON object, nothing else:

{
  "thought": "one short sentence of reasoning",
  "action": "click | type | select | upload | upload_any | press | goto | scroll | wait | done | fail",
  "index": 12,
  "text": "text to type, or option label for select",
  "key": "Enter",
  "url": "https://...",
  "seconds": 2,
  "pixels": 900,
  "path": "fixtures/pod.png",
  "summary": "what you accomplished",
  "result": { "any": "structured facts you actually saw" },
  "reason": "why you are blocked"
}

- "index" is required for click / type / select / upload / press.
- "path" is required for upload / upload_any.
- Use "upload_any" if the upload control is not in the element list (hidden file input).
- "done" only when PAGE TEXT visibly confirms the outcome.
- "fail" if blocked by OTP, CAPTCHA, email verification, or a page that never loads.
"""


class Agent:
    def __init__(self, name, role, session, creds, persona, tools_note=""):
        self.name = name
        self.role = role
        self.session = session
        self.creds = creds
        self.persona = persona
        self.tools_note = tools_note

    @property
    def system(self):
        return f"""You are the **{self.role}** in an automated multi-agent QA run against the live TAWSEEL delivery web application (a Vercel SPA). You drive a real browser.

{self.persona}

RULES
1. You act by choosing ONE action per turn, referring to elements by their index number.
2. When you land on a login screen, log in with the credentials given in YOUR CREDENTIALS.
3. Never claim success you cannot see. Only use "done" when PAGE TEXT confirms it.
4. If you are blocked by OTP, CAPTCHA, or a page that never loads, use "fail".
5. If the same action fails twice, change approach (scroll, goto the base URL, different element).
6. Stay in this browser session. Never try to open a new tab.
7. This is a QA test environment. Creating test orders and test data is expected and safe.
{self.tools_note}

{ACTION_DOC}"""

    def _user_prompt(self, task, context, snap, history, step, max_steps):
        els = "\n".join(
            f'{e["i"]}. <{e["tag"]}{(" type=" + e["type"]) if e["type"] else ""}> '
            f'label="{e["label"]}" name="{e["name"]}" '
            f'placeholder="{e["placeholder"]}" value="{e["value"]}"'
            for e in snap["elements"][:120]
        ) or "(no interactive elements found)"

        recent = json.dumps(history[-6:], indent=2) if history else "(none yet)"

        return f"""TASK
{task}

SHARED CONTEXT (same for all agents)
{json.dumps(context, indent=2, ensure_ascii=False)}

YOUR CREDENTIALS
email:    {self.creds.email}
password: {self.creds.password}

STEP {step + 1} of {max_steps}
CURRENT URL: {snap["url"]}
PAGE TITLE: {snap["title"]}

INTERACTIVE ELEMENTS (use the number as "index")
{els}

PAGE TEXT (truncated)
{snap["bodyText"]}

YOUR RECENT ACTIONS AND THEIR RESULTS
{recent}

Choose the single next action. JSON only."""

    def run_task(self, task, context, max_steps=25):
        history = []

        for step in range(max_steps):
            snap = self.session.snapshot()
            self.session.shot()

            try:
                d = decide(self.system, self._user_prompt(task, context, snap, history, step, max_steps))
            except Exception as e:
                history.append({"action": "llm_error", "result": str(e)[:200]})
                continue

            act = (d.get("action") or "").lower()

            if act == "done":
                return {
                    "status": "done",
                    "summary": d.get("summary", ""),
                    "result": d.get("result", {}),
                    "steps": step + 1,
                    "history": history,
                }

            if act == "fail":
                return {
                    "status": "failed",
                    "reason": d.get("reason", ""),
                    "steps": step + 1,
                    "history": history,
                }

            outcome = self.session.act(d)

            history.append({
                "action": act,
                "index": d.get("index"),
                "text": d.get("text"),
                "thought": d.get("thought", ""),
                "result": outcome,
            })
            history = history[-12:]

        return {"status": "timeout", "steps": max_steps, "history": history}
