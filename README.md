# Daily Warehouse Dashboard Email

Every day at **9:00 AM IST**, GitHub opens the live Warehouse Inventory dashboard, waits for the
Metabase numbers and the Unaccounted Item sheet to load, takes a full-page screenshot, and emails
it (inline + as an attachment) to your recipient list.

Nothing on the Netlify site changes. This runs entirely on GitHub's free scheduled jobs.

## Files

| File | What it does |
|---|---|
| `send_dashboard.py` | Takes the screenshot and sends the email |
| `.github/workflows/daily-dashboard-email.yml` | Runs the script daily at 03:30 UTC (9:00 AM IST) |
| `requirements.txt` | Python package list (Playwright browser) |

## One-time setup

### 1. Create the GitHub repository
1. Go to github.com → **New repository** → name it e.g. `warehouse-dashboard-email` → **Private** → Create.
2. Click **uploading an existing file**, drag in everything from this folder (including the `.github`
   folder), and commit.
   - If the `.github` folder doesn't upload by drag-and-drop, use **Add file → Create new file**, type
     `.github/workflows/daily-dashboard-email.yml` as the name, and paste the file's contents.

### 2. Get a password for the sending mailbox
The email is sent through a normal mailbox over SMTP. For a Google Workspace / Gmail account:
1. The account needs **2-Step Verification** turned on.
2. Go to **myaccount.google.com/apppasswords**, create an app password named "Dashboard email",
   and copy the 16-character password. (Your normal login password will not work.)

### 3. Add the settings as repository secrets
In the repo: **Settings → Secrets and variables → Actions → New repository secret**. Add:

| Secret | Value |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | the sending mailbox, e.g. `reports@virventures.com` |
| `SMTP_PASSWORD` | the 16-character app password from step 2 |
| `MAIL_TO` | the recipients, comma-separated. Current list: `vijay.sharma@ergode.com` (add the others after a comma, e.g. `vijay.sharma@ergode.com, name@virventures.com`) |
| `MAIL_FROM` | optional, e.g. `Warehouse Dashboard <reports@virventures.com>` |

Secrets are encrypted and never shown in the code or logs.

### 4. Send a test now
**Actions** tab → **Daily dashboard email** → **Run workflow**. In about 2 minutes the 5 recipients
should get the email. Each run also keeps the screenshot for 7 days under the run's **Artifacts**.

## Changing things later
- **Recipients:** edit the `MAIL_TO` secret. No code change needed.
- **Time:** edit the `cron` line in the workflow file (times are in UTC; IST = UTC + 5:30).
  Weekdays only at 9:00 AM IST would be `30 3 * * 1-5`.
- **Dashboard address:** add a repository *variable* `DASHBOARD_URL` (defaults to the live Netlify site).

## Good to know
- GitHub sometimes starts scheduled runs a few minutes late at busy times.
- GitHub pauses scheduled jobs in repos with no activity for 60 days. If that happens, it emails the
  repo owner and one click on **Enable workflow** turns it back on.
- If Metabase or the sheet doesn't load in time, the script retries once and still sends the email,
  with a note at the top saying which data didn't load.
