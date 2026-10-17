import os
from config import ARTIFACT_DIR

# Number every interactive element on the page so the LLM can refer to it by index.
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

    const raw = el.innerText || el.value || el.placeholder ||
                el.getAttribute('aria-label') || el.name || el.title || '';
    const label = String(raw).trim().replace(/\s+/g, ' ').slice(0, 120);

    el.setAttribute('data-tw-idx', String(idx));
    out.push({
      i: idx,
      tag: el.tagName.toLowerCase(),
      type: el.type || '',
      label: label,
      name: el.name || '',
      placeholder: el.placeholder || '',
      value: ('value' in el) ? String(el.value || '').slice(0, 60) : '',
    });
    idx++;
    if (idx >= 150) break;
  }

  return {
    url: location.href,
    title: document.title,
    elements: out,
    bodyText: (document.body ? document.body.innerText : '')
      .replace(/\n{2,}/g, '\n').slice(0, 4000),
  };
}
"""

class BrowserSession:
    """One independent logged-in browser session per agent."""

    def __init__(self, name, browser):
        self.name = name
        self.context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        self.page = self.context.new_page()
        self.step = 0

    # ---------- observation ----------

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

    # ---------- action ----------

    def act(self, a):
        kind = (a.get("action") or "").lower()
        idx = a.get("index")
        sel = f'[data-tw-idx="{idx}"]' if idx is not None else None

        try:
            if kind == "goto":
                self.goto(a["url"])

            elif kind == "click":
                # force=True ensures React doesn't block the click if another element is overlapping
                self.page.click(sel, timeout=10000, force=True)
                self.page.wait_for_timeout(1400)

            elif kind == "type":
                loc = self.page.locator(sel)
                loc.click(timeout=10000)
                # Clear the field first
                loc.press("Control+A")
                loc.press("Backspace")
                # Type slowly like a human so React registers the state change
                loc.press_sequentially(a.get("text", ""), delay=100)
                # Blur the field so React processes the input
                loc.press("Tab")
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
                # element is a visible file input
                self.page.set_input_files(sel, a["path"], timeout=10000)
                self.page.wait_for_timeout(1500)

            elif kind == "upload_any":
                # fallback: hidden <input type=file> not in our snapshot
                self.page.locator('input[type="file"]').first.set_input_files(
                    a["path"], timeout=10000
                )
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
