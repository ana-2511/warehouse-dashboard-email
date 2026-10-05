"""
Daily Warehouse Dashboard email.

Opens the live dashboard in a headless browser, waits for the Metabase data and the
Unaccounted Item sheet to load, takes a full-page screenshot, and emails it to the
recipient list. Runs every day from GitHub Actions (see .github/workflows/).

All settings come from environment variables (GitHub repository secrets):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD   - the mailbox that sends the email
  MAIL_FROM                                         - optional, defaults to SMTP_USER
  MAIL_TO                                           - comma-separated recipient list
  DASHBOARD_URL                                     - optional, defaults to the live site
"""

import os
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import make_msgid

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

DASHBOARD_URL = os.environ.get("DASHBOARD_URL") or "https://warehousedashboardvirventures.netlify.app/"
SCREENSHOT_PATH = "dashboard.png"
IST = timezone(timedelta(hours=5, minutes=30))


def capture(url: str, path: str) -> dict:
    """Screenshot the dashboard once its data has loaded. Returns load status details."""
    status = {"metabase": "unknown", "sheet": "unknown"}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1.5)

        for attempt in (1, 2):  # one retry with a fresh load if the data is slow
            page.goto(url, wait_until="networkidle", timeout=90_000)
            try:
                # Metabase finished (badge left the loading states)
                page.wait_for_function(
                    """() => {
                        const t = (document.getElementById('dataStatus') || {}).innerText || '';
                        return t && !/Initializing|Querying/i.test(t);
                    }""",
                    timeout=90_000,
                )
                # Unaccounted Item sheet finished (card left the loading states)
                page.wait_for_function(
                    """() => {
                        const el = document.getElementById('kpiUnaccountedSub');
                        if (!el) return true;  // older dashboard version without the sheet card
                        const s = el.innerText || '';
                        return s && !/Loading|Syncing/i.test(s);
                    }""",
                    timeout=60_000,
                )
            except PWTimeout:
                print(f"Attempt {attempt}: dashboard did not finish loading in time.")
                continue

            badge = page.inner_text("#dataStatus").strip()
            sheet_el = page.query_selector("#kpiUnaccountedSub")
            sheet = sheet_el.inner_text().strip() if sheet_el else "n/a"
            status = {"metabase": badge, "sheet": sheet}
            if "Live Metabase" in badge and "unavailable" not in sheet.lower():
                break
            print(f"Attempt {attempt}: partial data (badge='{badge}', sheet='{sheet}').")

        page.wait_for_timeout(2_000)  # let chart animations settle
        page.screenshot(path=path, full_page=True)
        browser.close()
    return status


def build_email(status: dict) -> EmailMessage:
    now = datetime.now(IST)
    recipients = [a.strip() for a in os.environ["MAIL_TO"].split(",") if a.strip()]
    sender = os.environ.get("MAIL_FROM") or os.environ["SMTP_USER"]

    msg = EmailMessage()
    msg["Subject"] = f"Warehouse Inventory Dashboard: {now:%d %b %Y}"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    live_ok = "Live Metabase" in status.get("metabase", "") and "unavailable" not in status.get("sheet", "").lower()
    warning = "" if live_ok else (
        f"<p style='color:#B42318;margin:0 0 12px'><b>Note:</b> some data did not load live at capture time "
        f"(Metabase: {status.get('metabase')}; Sheet: {status.get('sheet')}). "
        f"Open the dashboard for current figures.</p>"
    )

    img_cid = make_msgid(domain="virventures.dashboard")
    msg.set_content(
        f"Warehouse Inventory Dashboard snapshot for {now:%d %b %Y, %I:%M %p} IST.\n"
        f"Live dashboard: {DASHBOARD_URL}\n"
        f"The screenshot is attached."
    )
    msg.add_alternative(
        f"""<html><body style="font-family:Arial,sans-serif;color:#1F2328">
<p style="margin:0 0 12px">Hello,</p>
<p style="margin:0 0 12px">Here is today's Warehouse Inventory Dashboard snapshot,
captured {now:%d %b %Y, %I:%M %p} IST.</p>
{warning}
<p style="margin:0 0 16px"><a href="{DASHBOARD_URL}">Open the live dashboard</a></p>
<img src="cid:{img_cid[1:-1]}" alt="Warehouse Inventory Dashboard" style="max-width:100%;border:1px solid #D0D7DE">
</body></html>""",
        subtype="html",
    )
    with open(SCREENSHOT_PATH, "rb") as f:
        png = f.read()
    # inline image for the email body
    msg.get_payload()[1].add_related(png, maintype="image", subtype="png", cid=img_cid)
    # plus a normal attachment for easy saving/forwarding
    msg.add_attachment(png, maintype="image", subtype="png",
                       filename=f"warehouse-dashboard-{now:%Y-%m-%d}.png")
    return msg, recipients


def send(msg: EmailMessage, recipients: list):
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT") or 587)
    user, password = os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"]
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=60) as s:
            s.login(user, password)
            s.send_message(msg, to_addrs=recipients)
    else:
        with smtplib.SMTP(host, port, timeout=60) as s:
            s.starttls()
            s.login(user, password)
            s.send_message(msg, to_addrs=recipients)


if __name__ == "__main__":
    st = capture(DASHBOARD_URL, SCREENSHOT_PATH)
    print("Capture status:", st)
    if os.environ.get("SKIP_EMAIL") == "1":
        print("SKIP_EMAIL=1, screenshot saved only.")
        sys.exit(0)
    message, to = build_email(st)
    send(message, to)
    print(f"Sent to {len(to)} recipient(s).")
