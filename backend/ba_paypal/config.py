USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.7871.46 Safari/537.36"
)

SCREEN = {
    "colorDepth": 24,
    "pixelDepth": 24,
    "height": 864,
    "width": 1536,
    "availHeight": 864,
    "availWidth": 1536,
}

VIEWPORT = {"width": 1365, "height": 768}

# Keep every synthetic browser signal on the same regional/device profile.
# The checkout flow is hard-coded for Brazil, so timezone, locale, analytics,
# FraudNet and Client-Hints must all agree.
BROWSER_PROFILE = {
    "country": "BR",
    "language": "pt-BR",
    "locale": "pt_BR",
    "timezone": "America/Sao_Paulo",
    # JavaScript Date#getTimezoneOffset for UTC-3 is +180 minutes.
    "timezone_offset_minutes": 180,
    # FraudNet p1 uses millisecond offset in the same sign as getTimezoneOffset.
    "timezone_offset_ms": 180 * 60 * 1000,
    "dst": False,
    "chrome_major": 150,
    "chrome_full_version": "150.0.7871.46",
    "platform": "Linux x86_64",
    "sec_ch_platform": '"Linux"',
    "sec_ch_platform_version": '""',
    "sec_ch_arch": '"x86"',
    "device_memory": 8,
    "hardware_concurrency": 12,
    "device_pixel_ratio": 1,
    "connection_effective_type": "4g",
    "connection_rtt": "150",
    "connection_downlink": "10",
    "gpu_vendor": "Google Inc. (Google)",
    "gpu_renderer": (
        "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) "
        "(0x0000C0DE)), SwiftShader driver)"
    ),
    "webgl_vendor": "WebKit",
    "webgl_renderer": "WebKit WebGL",
}

TEALEAF_APP_KEY = "76938917d7504ff7a962174c021690bd"
HCAPTCHA_SITEKEY = "884d15d9-b649-4bbb-8d1c-2d6f0eed75eb"


# Browser fingerprint source：
#   "random" Continue to use the randomness synthesized in the program/template fingerprint；
#   "roxy"   pass RoxyBrowser Local API Create a random fingerprint window，From the truth again Chromium
#            runtime read canvas/WebGL/audio/heap/screen/UA Waiting for signal；
#   "headless" Use this machine Playwright headless Chromium read runtime Signal；
#   "auto"   When configured Roxy API key time priority Roxy，Otherwise fall back random。
# Available at runtime PAYPAL_FINGERPRINT_SOURCE cover。
FINGERPRINT_SOURCE = "random"

# RoxyBrowser Local API。Don't take the truth API key Submit to warehouse，Prioritize .env：
#   PAYPAL_FINGERPRINT_SOURCE=roxy
#   PAYPAL_ROXY_API_KEY=xxxx
#   PAYPAL_ROXY_API_PORT=50000
ROXY_API_HOST = "127.0.0.1"
ROXY_API_PORT = 50000
ROXY_API_KEY = ""
# Roxy Local API of /browser/open support headless Field；Roxy Mode uses headless mode by default。
ROXY_HEADLESS = True

# Optional：fixed workspace/project；Automatically read when empty /browser/workspace first item。
ROXY_WORKSPACE_ID: int | None = None
ROXY_PROJECT_ID: int | None = None


# DataDome processing mode：
#   "protocol" Preserve original protocol edge emulation：extract datadome client id，and without
#              datadome cookie injected when x-datadome-clientid；
#   "roxy"     Use the same one above Roxy Fingerprint browser loading PayPal/DataDome，make it real
#              Chrome runtime implement ddbm2/paypal challenge Chain and feed back cookie；
#   "headless" Use this machine Playwright headless Chromium implement DataDome chain；
#   "auto"     meet 403/authchallenge Or missing cookie time priority Roxy，Fallback after failure protocol；
#   "off"      Not proactively handling DataDome。
# Available at runtime PAYPAL_DATADOME_MODE cover。
DATADOME_MODE = "protocol"
DATADOME_ROXY_WAIT_SECONDS = 12.0


# MTR sealedResult source：
#   "python_generated" Keep the original agreement template for submission；
#   "roxy"             use the same Roxy Fingerprint browser loading PayPal page/dfp.js，
#                      Monitor the truth `/mtr/.../x0` and `/mtr/...` POST respond and feed back
#                      requestId/sealedResult/cookies；
#   "headless"         Use this machine Playwright headless Chromium implement dfp.js；
#   "auto"             priority roxy，Fallback after failure python_generated；
#   "off"              Do not send MTR。
# Available at runtime PAYPAL_MTR_RUNTIME cover。
MTR_RUNTIME_MODE = "python_generated"
MTR_ROXY_WAIT_SECONDS = 20.0

# MTR dfpconfig fallback.  new version PayPal Pages are sometimes no longer directly above the fold HTML
# output `<script id="dfpconfig">`，but dfp.js still needed channel/cmid/api key。
# Read pages first during runtime/RSC/Browser DOM in dfpconfig；below API key only as
# User explicit manual override，No more built-in fixed values：
#   PAYPAL_MTR_CHANNEL=iwc-mxo
#   PAYPAL_MTR_API_KEY=...
MTR_CHANNEL = "iwc-mxo"
MTR_API_KEY = ""


# signup-context browser risk source。The main process has been removed and independent Phase 1 Risk control signal steps。
#   "roxy"     use the same Roxy Fingerprint browser execution signup-context browser risk；
#   "headless" Use this machine Playwright headless Chromium；
#   "auto"     priority roxy，Roxy Fallback when unavailable headless。
# Available at runtime PAYPAL_RISK_SIGNALS_MODE cover。
# PAYPAL_ENABLE_SIGNUP_CONTEXT_RISK It's an old switch，Close is no longer allowed Step 3 Risk control。
RISK_SIGNALS_MODE = "protocol"
RISK_ROXY_WAIT_SECONDS = 18.0
