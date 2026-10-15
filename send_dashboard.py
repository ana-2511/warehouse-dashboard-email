"""
Weekly Warehouse Stock In vs Stock Out email.

Opens the live dashboard in a headless browser, waits until the data has loaded,
captures the Stock IN vs Stock OUT + Transfers chart as one sharp, uncropped image
and emails it in the body, with a link to the live dashboard.

Runs every Monday at 9:00 AM IST from GitHub Actions (.github/workflows/).
Sends the Stock IN vs Stock OUT + Transfers chart with a link to the live dashboard.

Settings (GitHub repository secrets):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD  - the sending mailbox (team@virventures.com)
  MAIL_FROM      optional display sender, defaults to "Warehouse Team - Virventures <SMTP_USER>"
  DASHBOARD_URL  optional (repository variable), defaults to the live site
Recipients are set in RECIPIENTS below (edit this file to change them).
"""

import os
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import make_msgid

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ---------------------------------------------------------------- recipients
PANKAJ_EMAIL = ""  # TODO: put Pankaj's email address here, e.g. "pankaj@ergode.com"

RECIPIENTS = {
    "to": ["rupesh@ergodeinc.com"],
    "cc": [
        "ankush.l@ergode.com",
        "pankaj.r@virventures.com,
        "rohitash.s@virventures.com",
        "akash.sonar@virventures.com",
        "vijay.sharma@ergode.com",
    ],
}
RECIPIENTS["cc"] = [e for e in RECIPIENTS["cc"] if e]  # skips any address left blank

DASHBOARD_URL = os.environ.get("DASHBOARD_URL") or "https://warehousedashboardvirventures.netlify.app/"
IST = timezone(timedelta(hours=5, minutes=30))
OUT_DIR = "shots"

# Dashboard sections to capture, found by a heading inside each one.
SECTIONS = [
    ("workflow", "Combined Workflow"),   # Stock IN vs Stock OUT + Transfers chart
]

WAIT_JS = """() => {
  const txt = id => ((document.getElementById(id) || {}).innerText || '');
  const has = id => !!document.getElementById(id);
  const metabase = txt('dataStatus') && !/Initializing|Querying/i.test(txt('dataStatus'));
  const sheet = !has('kpiUnaccountedSub') || !/Loading|Syncing/i.test(txt('kpiUnaccountedSub'));
  const zoho = !has('zohoStatus') || !/Loading|Syncing/i.test(txt('zohoStatus'));
  const chart = !has('heroRange') || txt('heroRange').trim().length > 0;
  return metabase && sheet && zoho && chart;
}"""


def capture(url: str) -> dict:
    """Load the dashboard, wait for live data, save one PNG per section + a full page."""
    os.makedirs(OUT_DIR, exist_ok=True)
    status = {"metabase": "unknown", "sheet": "unknown", "zoho": "unknown"}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # 1100px wide: close to the width the email shows the images at (1000px), so labels
        # are not shrunk, while the chart still shows 26 weeks. Scale 2 = crisp text.
        page = browser.new_page(viewport={"width": 1100, "height": 1000}, device_scale_factor=2)

        for attempt in (1, 2, 3):
            page.goto(url, wait_until="networkidle", timeout=120_000)
            try:
                page.wait_for_function(WAIT_JS, timeout=120_000)
            except PWTimeout:
                print(f"Attempt {attempt}: dashboard did not finish loading in time.")
                continue
            status = page.evaluate("""() => ({
                metabase: (document.getElementById('dataStatus') || {}).innerText || 'n/a',
                sheet: (document.getElementById('kpiUnaccountedSub') || {}).innerText || 'n/a',
                zoho: (document.getElementById('zohoStatus') || {}).innerText || 'n/a'})""")
            status = {k: v.strip() for k, v in status.items()}
            if is_live(status):
                break
            print(f"Attempt {attempt}: partial data {status}, retrying.")

        # Let fonts load and chart animations finish, and keep the sticky header out of section shots.
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(2500)
        page.add_style_tag(content="header{position:static !important}")

        for key, heading in SECTIONS:
            loc = page.locator("main > div").filter(has_text=heading).first
            if loc.count() == 0:
                print(f"Section '{heading}' not found, skipped.")
                continue
            loc.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            loc.screenshot(path=f"{OUT_DIR}/{key}.png", animations="disabled")

        page.screenshot(path=f"{OUT_DIR}/full-dashboard.png", full_page=True, animations="disabled")
        browser.close()
    return status


def is_live(st: dict) -> bool:
    # The Stock IN vs Stock OUT chart comes from Metabase only.
    return "Live Metabase" in st.get("metabase", "")


def img_tag(cid: str, alt: str) -> str:
    return (f'<img src="cid:{cid[1:-1]}" alt="{alt}" width="1000" '
            f'style="width:100%;max-width:1000px;height:auto;display:block;'
            f'border:1px solid #D0D7DE;border-radius:6px;margin:8px 0 18px 0">')


def build_email(status: dict):
    now = datetime.now(IST)
    smtp_user = os.environ["SMTP_USER"]
    sender = os.environ.get("MAIL_FROM") or f"Warehouse Team - Virventures <{smtp_user}>"

    chart = f"{OUT_DIR}/workflow.png"
    cid = make_msgid(domain="virventures.dashboard")

    msg = EmailMessage()
    msg["Subject"] = f"Warehouse Stock In vs Stock Out - {now:%d %b %Y}"
    msg["From"] = sender
    msg["To"] = ", ".join(RECIPIENTS["to"])
    if RECIPIENTS["cc"]:
        msg["Cc"] = ", ".join(RECIPIENTS["cc"])

    warning = "" if is_live(status) else (
        '<p style="color:#B42318;margin:0 0 14px"><b>Note:</b> live Metabase data did not load at capture '
        f'time ({status.get("metabase")}). Please check the live dashboard for current figures.</p>')

    p = 'style="margin:0 0 14px;line-height:1.5"'
    chart_html = (f'<img src="cid:{cid[1:-1]}" alt="Stock IN vs Stock OUT + Transfers Combined Workflow" width="1000" '
                  'style="width:100%;max-width:1000px;height:auto;display:block;'
                  'border:1px solid #D0D7DE;border-radius:6px;margin:8px 0 18px 0">') if os.path.exists(chart) else ""
    html = f"""<html><body style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#1F2328">
{warning}
<p {p}>Hello Everyone,</p>
<p {p}>Warehouse weekly Stock In vs Stock Out update is provided below:</p>
{chart_html}
<p {p}>Live dashboard: <a href="{DASHBOARD_URL}">{DASHBOARD_URL}</a></p>
<p {p}>Best regards,<br>Warehouse Team - Virventures</p>
</body></html>"""

    msg.set_content(
        "Hello Everyone,\n\nWarehouse weekly Stock In vs Stock Out update is provided below:\n"
        "(the chart is shown in the HTML version of this email)\n\n"
        f"Live dashboard: {DASHBOARD_URL}\n\nBest regards,\nWarehouse Team - Virventures")
    msg.add_alternative(html, subtype="html")
    if chart_html:
        with open(chart, "rb") as f:
            msg.get_payload()[1].add_related(f.read(), maintype="image", subtype="png", cid=cid)
    return msg, RECIPIENTS["to"] + RECIPIENTS["cc"]


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
    st = capture(DASHBOARD_URL)
    print("Capture status:", st)
    if os.environ.get("SKIP_EMAIL") == "1":
        print("SKIP_EMAIL=1, screenshots saved only.")
        sys.exit(0)
    message, to = build_email(st)
    send(message, to)
    print(f"Sent to {len(to)} recipient(s).")
