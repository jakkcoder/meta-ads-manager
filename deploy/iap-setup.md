# Access setup for Meta Ads Manager on Cloud Run

Service: `meta-ads-manager` · Region: `asia-south1` · Project: `vertex-ai-learning-487906`

## Error: redirect_uri_mismatch

The OAuth client is missing the IAP redirect URI (or it has a typo).

1. Open your client:  
   https://console.cloud.google.com/auth/clients/954888342020-hqf98878heoeg8piia83sn0gjuci533n.apps.googleusercontent.com?project=vertex-ai-learning-487906

2. Under **Authorized redirect URIs**, add **exactly**:

   ```
   https://iap.googleapis.com/v1/oauth/clientIds/954888342020-hqf98878heoeg8piia83sn0gjuci533n.apps.googleusercontent.com:handleRedirect
   ```

3. **Save** — wait 1–2 minutes, then retry in incognito.

4. On the consent screen, add your Gmail as a **Test user**:  
   https://console.cloud.google.com/auth/audience?project=vertex-ai-learning-487906

Also ensure that Google account has access:

```bash
./deploy/grant-access.sh jayudemy23@gmail.com
```

---

## Error: "Empty Google Account OAuth client ID(s)/secret(s)"

IAP was enabled **without** OAuth credentials. On personal GCP projects, `gcloud --iap` alone cannot create OAuth clients — you must configure them once, then use `gcloud` for everything else.

---

## Fix (recommended): Console OAuth client + gcloud script

### Step 1 — OAuth consent screen (one time, if not done)

https://console.cloud.google.com/auth/audience?project=vertex-ai-learning-487906

- **User type:** External  
- **Test users:** add `jayshankar.me1@gmail.com` (and any other `@gmail.com` users)

### Step 2 — Create OAuth Web client (one time)

https://console.cloud.google.com/auth/clients?project=vertex-ai-learning-487906

1. **Create client** → **Web application**  
2. Name: `Meta Ads Manager IAP`  
3. **Authorized redirect URIs** — paste this **exactly** (no spaces, no trailing slash):

   ```
   https://iap.googleapis.com/v1/oauth/clientIds/954888342020-hqf98878heoeg8piia83sn0gjuci533n.apps.googleusercontent.com:handleRedirect
   ```

   Direct edit link for your client:  
   https://console.cloud.google.com/auth/clients/954888342020-hqf98878heoeg8piia83sn0gjuci533n.apps.googleusercontent.com?project=vertex-ai-learning-487906

4. Copy **Client ID** and **Client secret**

### Step 3 — Apply with gcloud

```bash
chmod +x deploy/setup-iap-oauth.sh

./deploy/setup-iap-oauth.sh YOUR_CLIENT_ID YOUR_CLIENT_SECRET jayshankar.me1@gmail.com
```

This will:

- Set project-level IAP OAuth settings  
- Enable IAP on Cloud Run  
- Grant `roles/run.invoker` to the email(s)

### Step 4 — Open the app

https://meta-ads-manager-lmquvtnfja-el.a.run.app/cmo/

Sign in with the allowlisted Google account.

---

## Alternative: Console-only IAP (no manual client)

If you prefer not to copy client ID/secret:

1. Open Cloud Run: https://console.cloud.google.com/run/detail/asia-south1/meta-ads-manager/security?project=vertex-ai-learning-487906  
2. **Security** → **Authentication** → enable **Identity-Aware Proxy**  
   (Google auto-creates the OAuth client for you)  
3. Add users with **Cloud Run Invoker**  
4. For more users later: `./deploy/grant-access.sh email@gmail.com`

---

## Allowlist more users (after OAuth is configured)

```bash
./deploy/grant-access.sh jayshankar.me1@gmail.com jayudemy23@gmail.com
```

---

## Manual gcloud equivalent

```bash
PROJECT=vertex-ai-learning-487906
REGION=asia-south1
SERVICE=meta-ads-manager

cat > /tmp/iap_settings.yaml <<EOF
access_settings:
  oauth_settings:
    client_id: YOUR_CLIENT_ID
    client_secret: YOUR_CLIENT_SECRET
EOF

gcloud iap settings set /tmp/iap_settings.yaml --project=$PROJECT

gcloud beta run services update $SERVICE \
  --project=$PROJECT --region=$REGION --iap

gcloud run services add-iam-policy-binding $SERVICE \
  --project=$PROJECT --region=$REGION \
  --member="user:jayshankar.me1@gmail.com" \
  --role="roles/run.invoker"
```

---

## URLs

- App: https://meta-ads-manager-lmquvtnfja-el.a.run.app  
- CMO Dashboard: https://meta-ads-manager-lmquvtnfja-el.a.run.app/cmo/

## Cloud Scheduler

Uses `meta-ads-manager-sa` with `roles/run.invoker` — no user OAuth needed.
