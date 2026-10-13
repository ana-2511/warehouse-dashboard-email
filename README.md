# Daily Warehouse Dashboard Email

Every day at **9:00 AM IST** GitHub Actions opens the live dashboard
(https://warehousedashboardvirventures.netlify.app/), waits for Metabase, the
Unaccounted Item Google Sheet and Zoho WMS to load, takes sharp, uncropped
screenshots of each section, and emails them in the Warehouse Team template.

- **From:** team@virventures.com (Warehouse Team - Virventures)
- **To:** bryan.f@ergode.com
- **CC:** ankush.l@ergode.com, vijay.sharma@ergode.com, rohitash.s@virventures.com,
  akash.sonar@virventures.com, rupesh@ergodeinc.com
- **Subject:** Unshipped and Unaccounted Inventory Update - <date>

Recipients live in `RECIPIENTS` at the top of `send_dashboard.py`. Edit that file to change them.

## Files

| File | Purpose |
|---|---|
| `send_dashboard.py` | Captures the dashboard and sends the email |
| `requirements.txt` | Python packages (Playwright) |
| `.github/workflows/daily-dashboard-email.yml` | The 9:00 AM IST schedule |

## GitHub secrets (Settings → Secrets and variables → Actions)

| Secret | Value |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | `team@virventures.com` |
| `SMTP_PASSWORD` | 16-letter app password created on the team@virventures.com Google account |
| `MAIL_FROM` | optional, `Warehouse Team - Virventures <team@virventures.com>` |

`MAIL_TO` is no longer used and can be deleted.

To create the app password: sign in as team@virventures.com, turn on 2-Step
Verification, then go to https://myaccount.google.com/apppasswords.

## Testing

Actions tab → **Daily dashboard email** → **Run workflow**. A test run sends
the real email to Bryan and all CC recipients. The screenshots are also kept with each
run under **Artifacts → dashboard-screenshots** for 7 days.
