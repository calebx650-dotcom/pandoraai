# Deploying IGH fireNspec to Fly.io

You already have: Apple Developer, Stripe, Fly.io, Resend, GitHub repo.

## 1. Push to GitHub (5 min)

From a terminal in the project folder:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

## 2. Install Fly CLI (one-time)

macOS:  `brew install flyctl`
Linux:  `curl -L https://fly.io/install.sh | sh`
Then:   `fly auth login`

## 3. Launch on Fly.io (10 min)

From the project folder:

```bash
fly launch --no-deploy --copy-config
```

When prompted:
- App name: `igh-firenspec` (or pick something else and update `fly.toml`)
- Region: `dfw` (Dallas, closest to IGH)
- Postgres: **No** (we're using SQLite on a volume for now)
- Redis:    No
- Deploy:   No

## 4. Create the persistent volume

```bash
fly volumes create igh_data --region dfw --size 1
```

This 1 GB volume holds the SQLite DB and uploaded photos. Costs ~$0.15/month.

## 5. Set secrets

```bash
# A long random string for Flask sessions
fly secrets set IGH_SECRET=$(openssl rand -hex 32)

# Resend API key (from https://resend.com/api-keys)
fly secrets set RESEND_API_KEY=re_xxxxxxxxxxxx

# Sender address — must be a verified domain in Resend
fly secrets set EMAIL_FROM='reports@ighsafety.com'
```

## 6. Deploy

```bash
fly deploy
```

First deploy takes ~3 min. When it finishes:

```bash
fly open
```

You're live. Test login (`inspector` / `igh2026`) and complete a test inspection end-to-end.

## 7. Add a custom domain (optional, ~10 min)

```bash
fly certs add app.ighsafety.com
fly certs show app.ighsafety.com
```

Add the CNAME record it shows you in your DNS host. Cert provisions in ~2 min.

## 8. Verify Resend domain

In Resend's dashboard, add `ighsafety.com` as a sending domain and add the DNS records they show you. Until that's verified, emails will fail with "domain not verified."

## 9. Change the demo passwords

SSH into the Fly machine:
```bash
fly ssh console
python -c "
from werkzeug.security import generate_password_hash
import sqlite3
c = sqlite3.connect('/data/firenspec.db')
c.execute('UPDATE users SET password_hash=? WHERE username=?',
          (generate_password_hash('YOUR-NEW-PASSWORD'), 'admin'))
c.commit()
"
exit
```

## 10. Test the email flow

Open a completed report in the app, click "Email this report" — Resend will deliver to the customer's inbox.

---

## Things that still need a human

- **Apple Developer:** verify your team in App Store Connect (24h)
- **Stripe:** complete business verification (don't need this until you charge)
- **Resend:** add and verify `ighsafety.com` (DNS propagation ~15 min)

## Troubleshooting

- `fly logs` to tail server logs
- `fly status` to see machine health
- `fly ssh console` to poke the running container
- If deploy fails on the first run, try `fly deploy --no-cache`
- DB lives at `/data/firenspec.db` on the volume — survives redeploys

## Next steps once it's live

1. Pilot with one inspector for a week
2. Add Capacitor wrapper to ship to App Store (separate guide)
3. Migrate to Postgres once you have >2 concurrent inspectors writing
4. Wire Stripe billing if you want subscription/usage pricing
