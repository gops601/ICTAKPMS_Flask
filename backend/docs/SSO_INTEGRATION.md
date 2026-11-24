# ICTAK – Portal Integration Guide (SSO + batch/student enrolment)

This guide is for the developers of **another website/portal** that wants to

1. **send its batches and students** to ICTAK (so they appear here automatically), and
2. **sign those students in to ICTAK with one click** (single sign-on, SSO).

Everything is signed with one **shared secret** that an ICTAK administrator creates under
**Admin → Portal Connections → Connect a portal**. The secret is shown once; keep it on your server only,
never in browser code.

Live, interactive API documentation (Swagger UI) is always available at **`<ICTAK-URL>/api/docs`**.
A ready-made configuration file for your portal can be downloaded from the Portal Connections page
(**Download configuration** – JSON or `.env`).

---

## 0. What you need from ICTAK

| Item | Where it comes from | Example |
| --- | --- | --- |
| `ICTAK_URL` | The address of this portal | `https://pms.ictak.example` |
| `PORTAL_ID` (slug) | Shown on the connection card | `ictak-learn` |
| `SHARED_SECRET` | Shown once when the portal is connected (or after **New secret**) | `k3J…` (43 chars) |

Your side needs to be able to compute **HMAC-SHA256** and sign **HS256 JWTs**. Every language has libraries for both.

---

## 1. Enrol batches and students (push)

Call this whenever batches/students are created or changed in your portal (or on a schedule). It is **idempotent**:
sending the same data again updates instead of duplicating.

```
POST {ICTAK_URL}/api/integrations/{PORTAL_ID}/enrollments
Content-Type: application/json
X-Signature: sha256=<hex HMAC-SHA256 of the raw request body, key = SHARED_SECRET>
```

### Body

```json
{
  "batches": [
    {
      "code": "EXT-101",
      "name": "Full Stack – January 2026",
      "domain": "AIML",
      "ou": "ICTAK",
      "start_date": "2026-01-05",
      "end_date": "2026-06-30",
      "details": { "programme_name": "Full Stack" },
      "students": [
        { "name": "Asha K", "email": "asha@example.com", "registration_no": "R-001", "phone": "9999999999" },
        { "name": "Ben J",  "email": "ben@example.com" }
      ]
    }
  ]
}
```

| Field | Required | Notes |
| --- | --- | --- |
| `batches[].code` | yes | **Your** id for the batch. Remembered, so later pushes update the same batch. |
| `batches[].name` | yes (new batch) | Display name. |
| `batches[].domain` | yes (new batch) | The **code or name** of a domain that already exists in ICTAK (e.g. `AIML`). Unknown domains are reported as a problem. |
| `batches[].ou` | no | Organisational unit code/name. Defaults to the OU chosen on the connection, else the first active OU. |
| `batches[].start_date`, `end_date` | no | `YYYY-MM-DD`. |
| `batches[].details` | no | Values for the OU's custom batch fields. Required *text* fields you leave out are filled with `Imported from <portal name>`; other required fields (dates, numbers, choices) must be sent, otherwise the batch is reported under `problems`. |
| `students[].email` | yes | Unique key for a student. |
| `students[].name` | yes (new student) | At least 2 characters. |
| `students[].registration_no` | no | Generated (`ICT_STU_XXXXXX`) when omitted. |
| `students[].phone` | no | |

Limits: 200 batches and 5 000 students per request.

### What ICTAK does

* **New batch** → created with an `ICT_<DOMAIN>_XXXXXX` code, the domain lead is notified (to set project dates), the domain's
  mentors are assigned automatically.
* **New student** → account created in that batch. Students are meant to sign in through SSO (section 2); an administrator can
  still issue a password from the batch page.
* A student already enrolled in a **different** batch, or an e-mail that belongs to a mentor/lead/admin, is **skipped and
  reported** – the rest of the request still succeeds.

### Response `200`

```json
{
  "success": true,
  "message": "Enrolments applied",
  "data": {
    "batches_created": 1, "batches_updated": 0,
    "students_created": 2, "students_updated": 0,
    "problems": []
  }
}
```

`problems` is a list of human-readable strings (e.g. `Batch EXT-101: domain 'XYZ' was not found here …`).

### Errors

| Status | Meaning |
| --- | --- |
| 401 | Missing/incorrect `X-Signature`, unknown portal id, or the connection is switched off |
| 413 | Payload too large |
| 422 | Body is not JSON / not shaped like `{"batches": [...]}` |
| 429 | Rate limit (60 requests per minute) |

### Signing examples

**curl**

```bash
BODY='{"batches":[{"code":"EXT-101","name":"Jan cohort","domain":"AIML","students":[{"name":"Asha K","email":"asha@example.com"}]}]}'
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SHARED_SECRET" | sed 's/^.* //')
curl -X POST "$ICTAK_URL/api/integrations/$PORTAL_ID/enrollments" \
     -H "Content-Type: application/json" -H "X-Signature: sha256=$SIG" -d "$BODY"
```

**Python**

```python
import hashlib, hmac, json, requests

body = json.dumps(payload).encode()                    # sign EXACTLY the bytes you send
sig = hmac.new(SHARED_SECRET.encode(), body, hashlib.sha256).hexdigest()
r = requests.post(f"{ICTAK_URL}/api/integrations/{PORTAL_ID}/enrollments", data=body,
                  headers={"Content-Type": "application/json", "X-Signature": f"sha256={sig}"})
print(r.json())
```

**Node.js**

```js
import crypto from 'node:crypto'
const body = JSON.stringify(payload)
const sig = crypto.createHmac('sha256', process.env.SHARED_SECRET).update(body).digest('hex')
const res = await fetch(`${ICTAK_URL}/api/integrations/${PORTAL_ID}/enrollments`, {
  method: 'POST', body, headers: { 'Content-Type': 'application/json', 'X-Signature': `sha256=${sig}` },
})
console.log(await res.json())
```

**PHP**

```php
$body = json_encode($payload);
$sig  = hash_hmac('sha256', $body, $SHARED_SECRET);
$ch = curl_init("$ICTAK_URL/api/integrations/$PORTAL_ID/enrollments");
curl_setopt_array($ch, [CURLOPT_POST => true, CURLOPT_POSTFIELDS => $body, CURLOPT_RETURNTRANSFER => true,
  CURLOPT_HTTPHEADER => ['Content-Type: application/json', "X-Signature: sha256=$sig"]]);
echo curl_exec($ch);
```

### Alternative: ICTAK pulls from you

If you would rather expose a feed, give ICTAK the **Portal base URL**, **feed path** (default `/api/enrollments`) and an
**API token** on the connection. **Sync now** then does `GET {base_url}{path}` with `Authorization: Bearer <token>` and expects
the same JSON body as above.

---

## 2. Single sign-on (student clicks a link in your portal)

1. Your server creates a **short-lived JWT** for the logged-in student, signed with `SHARED_SECRET` (**HS256**).
2. Your portal sends the browser to:

   ```
   {ICTAK_URL}/sso?portal={PORTAL_ID}&token={JWT}
   ```

3. ICTAK verifies the token, signs the student in and opens their dashboard. No password is ever shared.

### Token claims

| Claim | Required | Notes |
| --- | --- | --- |
| `email` | yes | The student's e-mail (must match the enrolled one – case-insensitive). |
| `exp` | yes | Expiry (Unix seconds). **At most 10 minutes** from now; generate the token at click time. |
| `iss` | no | If present it must equal `PORTAL_ID`. |
| `name`, `batch`, `reg_no` | no | **First-time sign-in only:** if the e-mail is unknown and `batch` is *your batch code* (`code` from section 1) the student is enrolled just-in-time (`name` required). |

Only students, mentors and domain leads can sign in this way. **Administrators cannot** (they use a password).
Deactivated accounts are refused.

**Python**

```python
import jwt, time
token = jwt.encode({"email": "asha@example.com", "iss": PORTAL_ID, "exp": int(time.time()) + 120},
                   SHARED_SECRET, algorithm="HS256")
redirect_to = f"{ICTAK_URL}/sso?portal={PORTAL_ID}&token={token}"
```

**Node.js** (`npm i jsonwebtoken`)

```js
import jwt from 'jsonwebtoken'
const token = jwt.sign({ email: 'asha@example.com', iss: PORTAL_ID }, SHARED_SECRET, { algorithm: 'HS256', expiresIn: '2m' })
res.redirect(`${ICTAK_URL}/sso?portal=${PORTAL_ID}&token=${token}`)
```

**PHP** (`composer require firebase/php-jwt`)

```php
use Firebase\JWT\JWT;
$token = JWT::encode(['email' => 'asha@example.com', 'iss' => $PORTAL_ID, 'exp' => time() + 120], $SHARED_SECRET, 'HS256');
header("Location: $ICTAK_URL/sso?portal=$PORTAL_ID&token=$token");
```

### API form (for apps that handle the redirect themselves)

```
POST {ICTAK_URL}/api/auth/sso        Content-Type: application/json
{ "portal": "ictak-learn", "token": "<JWT>" }
```

Response `200`: `{"data": {"access_token": "...", "refresh_token": "...", "user": {...}}}`.
Errors: `401` bad/expired/too-long-lived token, unknown or switched-off portal; `403` no account yet (and no valid `batch`
claim), administrator, or deactivated account; `429` more than 30 attempts per minute.

---

## 3. Security checklist

* Keep `SHARED_SECRET` **server-side only**; use HTTPS everywhere.
* Sign the **exact raw bytes** you send (re-serialising JSON changes the signature).
* Generate SSO tokens **at click time** with a 1–2 minute expiry.
* Rotate the secret from **Portal Connections → New secret** if it may have leaked – the old one stops working immediately.
* Disconnecting a portal stops SSO and pushes; batches/students already enrolled stay in ICTAK.
* Every push, sync and SSO sign-in is written to the audit log.

## 4. Testing it quickly

1. In ICTAK: **Admin → Portal Connections → Connect a portal**, copy the secret, download the configuration file.
2. Push the sample body from section 1 with curl. Check the new batch under **Admin → Batches** and the result on the
   connection card (**Last result**).
3. Build a token (section 2), open `{ICTAK_URL}/sso?portal=…&token=…` – you land on the student dashboard.
