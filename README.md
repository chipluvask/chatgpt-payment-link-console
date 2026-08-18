#tele : @tuttutfree_bot
# min-implant-v2

ChatGPT Subscription payment link automation research project(For study and research only, Please comply with the target platform’s terms of service and local laws)。

## Directory structure

```
backend/                 FastAPI rear end (Chain lifting engine / Direct card / PayPal BA / hCaptcha)
  core/                  core link engine (chain / oaics_proto / bind_card / proxy)
  api/                   REST API routing
  ba_paypal/             PayPal BA Authorization four-stage process (flow.py) + hCaptcha mint stack
    ba_fp_helpers/       Node bridge (happy-dom / hsw PoW) — need npm install
    sentinel_assets/     OpenAI Sentinel sign SDK — need npm install
    paypal/              PayPal Process module (flow / session / smsbower / identity_lib)
  config.yaml            ★ local configuration (gitignore, use config.example.yaml copy)
frontend/                React 19 + Vite 8 front panel (Source code, need npm install + build)
web/                     Management console static resources (index.html + static/ + dist/ Build product)
_archive_dev/            Development period test scripts and packet capture data (gitignore, Not released with the warehouse)
operations.bat            Windows operations menu (start/restart/log/build)
```

## Environmental requirements

| rely | Version | use | required |
|---|---|---|---|
| Python | >=3.10 | backend runtime | ✅ |
| Node.js | >=18 (suggestion 20) | OpenAI Sentinel mint (Node/V8 sdk bridge)、Front-end build | ✅ |
| proxy pool | See below | link egress (billing country/Exporting countries must align) | ✅ |
| SMSBower API key | See below | PayPal Authorize 2FA Receive code | ⚠️ only PayPal BA Wire |
| Clash/mihomo local agent | — | 711 residential pool relay prefix (127.0.0.1:7890/7897) | ⚠️ only 711 pool |

> Playwright (Optional): `backend/ba_paypal/paypal/recaptcha_solver.py` need, Go by default HTTP untie
> Can `pip install playwright` Enable alternate paths。

## one、Install

### 1. Python rely

```bash
cd backend
pip install -r requirements.txt
pip install -r ba_paypal/requirements.txt
```

### 2. Node rely (Three places)

```bash
cd backend/ba_paypal/ba_fp_helpers     && npm install
cd ../sentinel_assets                  && npm install
cd ../../..                            # Back to project root
cd frontend                            && npm install   # When you only need to change the front end
```

> `ba_paypal/` There is another one in the root directory package.json (@msgpack/msgpack), like Node Bridge report missing package
> together `npm install`。

### 3. Configuration file

```bash
# Backend configuration (proxy pool/port/Link parameters)
cd backend
copy config.example.yaml config.yaml     # Windows
cp config.example.yaml config.yaml       # Linux/macOS

# SMSBower Code receiving platform key (only PayPal BA Line required)
cd ba_paypal
copy .env.example .env                   # Windows
cp .env.example .env                     # Linux/macOS
```

edit `config.yaml`, At least fill in the proxy pool credentials (See below)。

### 4. Front-end build (Optional, web/dist Already provided with warehouse)

```bash
cd frontend
npm run build        # The product is output to ../web/dist, Backend direct service
```

## two、start up

### Windows

Double-click `operations.bat`. Menu options:
- `1` environmental inspection (port/healthy/proxy relay/log)
- `2` One-click restart (rear end + Front-end build)
- `4` Start backend (http://127.0.0.1:8770)

> Automatic detection of operation and maintenance scripts `python` / `node` (PATH or `PYTHON` / `NODE_BIN` environment variables),
> Log output to `%TEMP%\min-implant-v2\`。

### Manual

```bash
cd backend
python -m uvicorn app:app --host 0.0.0.0 --port 8770
# Open http://127.0.0.1:8770
```

## three、Detailed explanation of external resources required

### 1. proxy pool (required)

Each segment of the link uses independent exits IP, and**The billing country must be consistent with the exporting country** (otherwise Stripe 400
`Billing country must match request country`)。The project supports three types of agent sources:

| type | Configuration location | illustrate |
|---|---|---|
| **QG tunnel proxy** | `config.yaml → proxy.qg_super_pool / qg_resi_pool` | master agent pool, connection string `http://{auth_key}:{auth_pwd}:A{area}@host:port`, area Control exporting countries |
| **711 residential agency** | `config.yaml → proxy.proxy_711.enabled` + environment variables | Go local Clash/mihomo relay (7890/7897), sticky session by country, pass `PROXY_711_USER` / `PROXY_711_PASS` injection (No more hardcoding) |
| **sing-box node** | `core/proxy_pool.py` built-in | VLESS/Hysteria2 33 node (JP/HK/SG/US/KR/TW), local relay 18077-18117 |

needed things:
- one QG (or other) Tunnel proxy account: `auth_key` + `auth_pwd`, Support export selection by country
- (Optional) 711 Residential Agent Account: `USER` + `PASS` + local Clash client
- Agent usability testing: Operation and maintenance menu `1` or watch directly `uvicorn.log` of `[proxy_711] smoke`

### 2. Code receiving platform (SMSBower, only PayPal BA Wire)

PayPal register/2FA Requires mobile phone verification code。Project docking SMSBower:

```bash
# backend/ba_paypal/.env
SMSBOWER_API_KEY=yourkey
PAYPAL_SMSBOWER_API_KEY=yourkey
```

### 3. relay/local agent (only 711 pool)

711 pool link: `client → 127.0.0.1:18794 (relay) → Clash 7890/7897 → 711 → Target`。
Requires local running Clash system client (FlClash / Clash Verge), and turn on mixed-port。

### 4. OpenAI account token (running raw materials)

The link consumes ChatGPT session token (access_token + session_token), on the panel
"Token import" Medium batch import。**The account needs to be eligible for promotion** (plus-1-month-free) to get out
0 yuan chain, Unqualified account pressure 0 invalid。

## Four、List of environment variables

| variable | default | illustrate |
|---|---|---|
| `PYTHON` | `python` | For operation and maintenance scripts Python interpreter |
| `NODE_BIN` | `node` | For operation and maintenance scripts Node executable file |
| `SENTINEL_NODE` | `node` | Sentinel mint called Node |
| `PROXY_711_USER` | `YOUR_711_USER` | 711 Agent username |
| `PROXY_711_PASS` | `YOUR_711_PASS` | 711 Agent password |
| `PROXY_711_RELAY_PORT` | `18794` | 711 relay port |
| `MIN_TEST_CARD_NUMBER` | `4000000000000002` | Built-in test card number (Placeholder) |
| `MIN_TEST_CARD_EXP_MONTH` | `12` | Test card month |
| `MIN_TEST_CARD_EXP_YEAR` | `30` | test card year |
| `MIN_TEST_CARD_CVC` | `123` | test card CVC |
| `SMSBOWER_API_KEY` / `PAYPAL_SMSBOWER_API_KEY` | — | Code receiving platform (ba_paypal/.env) |
| `MIN_OAICS_ATTESTATION` | — | Manual injection OpenAI Front-end deployment proof (Skip crawling) |
| `MIN_OAICS_P1` | — | Manual injection Stripe hCaptcha P1 token |
| `MIN_OAICS_CUSTOMER` | — | Manual injection Stripe customer id |
| `MIN_OAICS_SENTINEL` | `0` Disabled when | Sentinel head switch |
| `PROXY_711_HOST` / `PROXY_711_PORT` | 711proxy.com:10000 | 711 Gateway coverage |

## Four·five、GPT Account registration (panel "resource → Account registration")

built-in ChatGPT Account registration function (`backend/reg/`)，protocol：next-auth OAuth → OTP →
sentinel create_account → access/session token。Automatically write successful account Token Library
(`source=register`)，Can be used directly to lift the chain。

**Built-in email channel**：`mailtm` (Zero dependency online API，default)。Automatically enabled when agent is left blank
711 residential relay。

**Access custom email channels**：Registration engine provides extension points，Any email source（IMAP / outlook
Mailbox pool / Self-built mailbox / Temporary mailbox API）All can access。exist `backend/app.py` Called at startup：

```python
from reg import engine as reg_engine

def setup_my_mailbox(proxies, cancel_check):
    # 1) Get an available registered email address
    email = claim_mailbox()                 # your implementation
    openai_password = "Aa1!xxxx"            # ≥12 bit random password
    # 2) Return to codec：Poll your inbox until you get it OpenAI OTP
    def fetch_code(timeout_sec=None, seen_ids=None, not_before=None):
        return wait_otp(email, timeout_sec)  # your implementation
    return email, openai_password, fetch_code

reg_engine.register_email_channel("my_mailbox", setup_my_mailbox)
```

Channel name after registration `my_mailbox` Automatically appears in the panel channel drop-down。`fetch_code` agreed with
`chatgpt_core.py` Built-in channels are consistent（`timeout_sec` / `seen_ids` / `not_before`
Parameter optional implementation）。The registration agreement itself（OAuth/OTP/sentinel/create_account）with mailbox
Source completely decoupled。

## five、Link overview

Project built-in **16 chain branch**, can be found on the panel "Link configuration" or `config.yaml → chain.branches.<name>.stages`
Adjust the seventh section exit (checkout/init/update/provider/approve/poll/resolve) and OAICS fifth section
(checkout/taxes/provider/confirm/resolve) mapping。

| branch | channel | billing country (default) | output |
|---|---|---|---|
| `paypal` | PayPal | auto | `paypal.com/agreements/approve?ba_token=...` |
| `direct` | Direct card | PH | Card binding + Subscription verification (SetupIntent inline) |
| `momo` | MoMo | auto | `payment.momo.vn/pay/app` Jump |
| `pix` | PIX QR code | auto | PIX Pay QR code |
| `ideal` | iDEAL | auto | iDEAL bank transfer |
| `upi` | UPI | auto | UPI Payment jump |
| `kakao` | Kakao Pay | auto | Kakao Payment jump |
| `blik` | BLIK | auto | BLIK Payment jump |
| `twint` | TWINT | auto | TWINT Payment jump |
| `bizum` | Bizum | auto | Bizum Payment jump |
| `gopay` | GoPay | auto | GoPay Payment jump |
| `qris` | QRIS | ID | QRIS QR code |
| `gcash` | GCash | PH | GCash Payment jump |
| `grabpay` | GrabPay | PH | GrabPay Payment jump |
| `naver_pay` | Naver Pay | auto | Naver Pay Payment jump |
| `grok` | Grok link | auto | card Channel promotion chain |

Core link form:
- **PayPal lift chain (paypal branch)**: checkout → taxes → provider → confirm → resolve,
  output `paypal.com/agreements/approve?ba_token=...`
- **PayPal BA Authorize (ba_paypal module)**: DataDome → Create an account → 2FA → authorize, output EUAT
- **Straight card line (direct branch)**: pure HTTP 9 step (checkout → SetupIntent inline → confirm → Subscription verification)
