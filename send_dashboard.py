"""
Daily Warehouse Dashboard email (Unshipped + Unaccounted Inventory).

Opens the live dashboard in a headless browser, waits until Metabase, the
Unaccounted Item Google Sheet and Zoho WMS have all loaded, then captures each
dashboard section as its own sharp image (element screenshots are never cropped)
and emails them inside the Warehouse Team template.

Runs every Monday at 9:00 AM IST from GitHub Actions (.github/workflows/).
The Zoho pending outgoing data (VVI_FBM) is attached as a CSV file.

Settings (GitHub repository secrets):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD  - the sending mailbox (team@virventures.com)
  MAIL_FROM      optional display sender, defaults to "Warehouse Team - Virventures <SMTP_USER>"
  DASHBOARD_URL  optional (repository variable), defaults to the live site
Recipients are set in RECIPIENTS below (edit this file to change them).
"""

import os
import smtplib
import urllib.request
import sys
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import make_msgid

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ---------------------------------------------------------------- recipients
RECIPIENTS = {
    "to": ["bryan.f@ergode.com"],
    "cc": [
        "ankush.l@ergode.com",
        "krishna.s@ergode.com",
        "pankaj.r@virventures.com",
        "vijay.sharma@ergode.com",
        "rohitash.s@virventures.com",
        "akash.sonar@virventures.com",
        "rupesh@ergodeinc.com",
      
    ],
}

DASHBOARD_URL = os.environ.get("DASHBOARD_URL") or "https://warehousedashboardvirventures.netlify.app/"
IST = timezone(timedelta(hours=5, minutes=30))
OUT_DIR = "shots"

# Dashboard sections to capture, found by a heading inside each one.
SECTIONS = [
    ("kpis", "Total Stock IN"),
    ("zoho", "Ageing Unshipped"),
    ("unaccounted", "Ageing Range of Unaccounted Item"),
    ("workflow", "Combined Workflow"),
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


def fetch_zoho_csv() -> bytes | None:
    """Download the Zoho pending outgoing rows as CSV from the dashboard's function."""
    url = DASHBOARD_URL.rstrip("/") + "/.netlify/functions/get-zoho?format=csv"
    for attempt in (1, 2, 3):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                if r.status == 200 and "csv" in (r.headers.get("Content-Type") or ""):
                    return r.read()
                print(f"Zoho CSV attempt {attempt}: unexpected response {r.status}")
        except Exception as e:  # noqa: BLE001
            print(f"Zoho CSV attempt {attempt} failed: {e}")
    return None


def is_live(st: dict) -> bool:
    return ("Live Metabase" in st.get("metabase", "")
            and "unavailable" not in st.get("sheet", "").lower()
            and "unavailable" not in st.get("zoho", "").lower()
            and "cached" not in st.get("zoho", "").lower())


def img_tag(cid: str, alt: str) -> str:
    return (f'<img src="cid:{cid[1:-1]}" alt="{alt}" width="1000" '
            f'style="width:100%;max-width:1000px;height:auto;display:block;'
            f'border:1px solid #D0D7DE;border-radius:6px;margin:8px 0 18px 0">')


def build_email(status: dict, zoho_csv: bytes | None = None):
    now = datetime.now(IST)
    smtp_user = os.environ["SMTP_USER"]
    sender = os.environ.get("MAIL_FROM") or f"Warehouse Team - Virventures <{smtp_user}>"

    shots = {k: f"{OUT_DIR}/{k}.png" for k, _ in SECTIONS if os.path.exists(f"{OUT_DIR}/{k}.png")}
    cids = {k: make_msgid(domain="virventures.dashboard") for k in shots}
    img = lambda k, alt: img_tag(cids[k], alt) if k in cids else ""

    msg = EmailMessage()
    msg["Subject"] = f"Unshipped and Unaccounted Inventory Update - {now:%d %b %Y}"
    msg["From"] = sender
    msg["To"] = ", ".join(RECIPIENTS["to"])
    if RECIPIENTS["cc"]:
        msg["Cc"] = ", ".join(RECIPIENTS["cc"])

    warning = "" if is_live(status) else (
        '<p style="color:#B42318;margin:0 0 14px"><b>Note:</b> some dashboard data did not load live '
        f'at capture time (Metabase: {status.get("metabase")}; Sheet: {status.get("sheet")}; '
        f'Zoho: {status.get("zoho")}). Please check the live dashboard for current figures.</p>')

    p = 'style="margin:0 0 14px;line-height:1.5"'
    zoho_name = f"zoho-pending-outgoing-VVI_FBM-{now:%Y-%m-%d}.csv"
    zoho_note = (f'<p style="margin:0 0 14px;font-size:13px;color:#57606A">The full list of pending outgoing '
                 f'orders is attached: <b>{zoho_name}</b></p>') if zoho_csv else ""
    h = 'style="margin:22px 0 8px;font-size:15px"'
    html = f"""<html><body style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#1F2328">
{warning}
<p {p}>Hi Bryan,</p>
<p {p}>Please find the pending details of Unshipped and Unaccounted Inventory for your reference and necessary action.</p>

<p {h}><b>1. Unshipped Inventory</b></p>
<p {p}>It is important to ensure that all unshipped inventory is dispatched at the earliest. We request you to maintain a 24-hour turnaround time (TAT) for processing and shipping these orders. Delays in shipment can negatively impact our marketplace On-Time Delivery Rate (OTDR) metrics and may result in negative customer feedback.</p>
{img("zoho", "Pending Outgoing and Ageing Unshipped")}
{zoho_note}

<p {h}><b>2. Unaccounted Inventory</b></p>
<p {p}>Vendors expect unaccounted inventory to be returned within seven days. Timely identification and processing of this inventory are essential to ensure it is returned to the respective vendors within the expected timeline. Additionally, the sooner the inventory is accounted for and made available in the system, the sooner we can list the products and make them available for sale.</p>
{img("unaccounted", "Ageing Range of Unaccounted Item")}

<p {p}>Our objective is to keep both unshipped and unaccounted inventory levels as low as possible through timely processing, regular monitoring, and prompt action.</p>
<p {p}>Your support in maintaining these timelines and ensuring consistent follow-up will be greatly appreciated.</p>
<p {p}>Best regards,<br>Warehouse Team - Virventures</p>

<hr style="border:none;border-top:1px solid #D0D7DE;margin:24px 0 12px">
<p style="margin:0 0 6px;font-size:12px;color:#57606A">Dashboard snapshot, {now:%d %b %Y, %I:%M %p} IST &bull; <a href="{DASHBOARD_URL}">Open the live dashboard</a></p>
{img("kpis", "Warehouse KPI summary")}
{img("workflow", "Stock IN vs Stock OUT + Transfers Combined Workflow")}
</body></html>"""

    msg.set_content(
        "Hi Bryan,\n\nPlease find the pending details of Unshipped and Unaccounted Inventory "
        "for your reference and necessary action. The dashboard images are included in the "
        f"HTML version of this email and attached.\n\nLive dashboard: {DASHBOARD_URL}\n\n"
        "Best regards,\nWarehouse Team - Virventures")
    msg.add_alternative(html, subtype="html")
    related = msg.get_payload()[1]
    for k, path in shots.items():
        with open(path, "rb") as f:
            related.add_related(f.read(), maintype="image", subtype="png", cid=cids[k])

    if zoho_csv:
        msg.add_attachment(zoho_csv, maintype="text", subtype="csv", filename=zoho_name)

    full = f"{OUT_DIR}/full-dashboard.png"
    if os.path.exists(full):
        with open(full, "rb") as f:
            msg.add_attachment(f.read(), maintype="image", subtype="png",
                               filename=f"warehouse-dashboard-{now:%Y-%m-%d}.png")
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
    csv_data = fetch_zoho_csv()
    if csv_data:
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(f"{OUT_DIR}/zoho-pending-outgoing.csv", "wb") as f:
            f.write(csv_data)
    if os.environ.get("SKIP_EMAIL") == "1":
        print("SKIP_EMAIL=1, screenshots and Zoho CSV saved only.")
        sys.exit(0)
    message, to = build_email(st, csv_data)
    send(message, to)
    print(f"Sent to {len(to)} recipient(s).")
