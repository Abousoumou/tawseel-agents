import os
from config import ARTIFACT_DIR

SNAPSHOT_JS = r"""
() => {
  document.querySelectorAll('[data-tw-idx]').forEach(e => e.removeAttribute('data-tw-idx'));
  const sel = 'a,button,input,select,textarea,[role="button"],[role="link"],[role="tab"],[onclick]';
  const out = [];
  let idx = 0;
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    const st = window.getComputedStyle(el);
    if (r.width <= 0 || r.height <= 0) continue;
    if (st.visibility === 'hidden' || st.display === 'none' || st.opacity === '0') continue;
    if (el.disabled) continue;
    const raw = el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || el.name || el.title || '';
    const label = String(raw).trim().replace(/\s+/g, ' ').slice(0, 120);
    el.setAttribute('data-tw-idx', String(idx));
    out.push({
      i: idx, tag: el.tagName.toLowerCase(), type: el.type || '', label: label,
      name: el.name || '', placeholder: el.placeholder || '',
      value: ('value' in el) ? String(el.value || '').slice(0, 60) : '',
    });
    idx++;
    if (idx >= 150) break;
  }
  return {
    url: location.href, title: document.title, elements: out,
    bodyText: (document.body ? document.body.innerText : '').replace(/\n{2,}/g, '\n').slice(0, 4000),
  };
}
"""

class BrowserSession:
    def __init__(self, name, browser):
        self.name = name
        # Disguise the bot as a real Android phone to bypass WAF blocks
        self.context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36"
        )
        self.page = self.context.new_page()
        self.step = 0

    def goto(self, url):
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_timeout(1800)

    def snapshot(self):
        return self.page.evaluate(SNAPSHOT_JS)

    def shot(self):
        self.step += 1
        d = os.path.join(ARTIFACT_DIR, self.name)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"{self.step:03d}.png")
        try:
            self.page.screenshot(path=path)
        except Exception:
            pass
        return path

    def act(self, a):
        kind = (a.get("action") or "").lower()
        idx = a.get("index")
        sel = f'[data-tw-idx="{idx}"]' if idx is not None else None

        try:
            if kind == "goto":
                self.goto(a["url"])

            elif kind == "click":
                # FORENSICS: Print the exact password length to the GitHub logs before clicking
                try:
                    email_val = self.page.evaluate("document.querySelector('input[type=\"email\"]')?.value || 'N/A'")
                    pass_val = self.page.evaluate("document.querySelector('input[type=\"password\"]')?.value || 'N/A'")
                    print(f"\n[DEBUG-FORM] Submitting form -> Email: '{email_val}' | Password Length: {len(pass_val)} (Expected: 13)\n", flush=True)
                except Exception:
                    pass

                self.page.click(sel, timeout=10000, force=True)
                self.page.wait_for_timeout(1400)

            elif kind == "type":
                text_to_type = a.get("text", "")
                # Use native JS to force React to accept the input
                self.page.evaluate("""([selector, value]) => {
                    const el = document.querySelector(selector);
                    if (!el) return;
                    el.focus();
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    nativeInputValueSetter.call(el, value);
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.blur();
                }""", [sel, text_to_type])
                self.page.wait_for_timeout(600)

            elif kind == "select":
                try:
                    self.page.select_option(sel, label=a.get("text"), timeout=8000)
                except Exception:
                    self.page.select_option(sel, value=a.get("text"), timeout=8000)
                self.page.wait_for_timeout(800)

            elif kind == "press":
                self.page.press(sel, a.get("key", "Enter"))
                self.page.wait_for_timeout(1400)

            elif kind == "upload":
                self.page.set_input_files(sel, a["path"], timeout=10000)
                self.page.wait_for_timeout(1500)

            elif kind == "upload_any":
                self.page.locator('input[type="file"]').first.set_input_files(a["path"], timeout=10000)
                self.page.wait_for_timeout(1500)

            elif kind == "scroll":
                self.page.mouse.wheel(0, int(a.get("pixels", 900)))
                self.page.wait_for_timeout(600)

            elif kind == "wait":
                self.page.wait_for_timeout(int(a.get("seconds", 2)) * 1000)

            elif kind in ("done", "fail"):
                pass

            else:
                return f"ERROR: unknown action '{kind}'"

            return "ok"

        except Exception as e:
            return f"ERROR: {type(e).__name__}: {str(e)[:220]}"

    def close(self):
        try:
            self.context.close()
        except Exception:
            pass
