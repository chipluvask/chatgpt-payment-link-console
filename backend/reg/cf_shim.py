# -*- coding: utf-8 -*-
"""
cf_shim.py — curl_cffi Session Gasket，Specialized in treating menstruation mihomo When acting as agent
intermittent BoringSSL "invalid library" / "TLS connect error"。

Phenomenon：same node、same agent，Occasionally TLS Handshake failed，Replace with a brand new one Session Just try again。
root cause：curl_cffi Reuse the bottom layer curl handle hour，Individual connections enter a bad state，BoringSSL throw
SSL_ERROR_INVALID_LIBRARY。How to fix it = Rebuild after catching this error Session（brand new handle）Try again。

usage（exist chatgpt.py inside）：
    from cf_shim import Session, requests
replace the original：
    from curl_cffi.requests import Session
    from curl_cffi import requests
"""
import time
from curl_cffi import requests as _creq
from curl_cffi.requests import Session as _CSession

# Error reporting characteristics that trigger retries
# Added proxy layer error（Proxy CONNECT aborted / ProxyError）：Residential proxy pool always press connection
# Rotate export IP，reconstruction Session Hou Xin CONNECT May fall into the trap of not being OpenAI edge cooled IP，
# thereby bypassing“The whole thing seems to be broken、In fact, a certain exit IP restricted”intermittent blocking of。
_RETRY_HINTS = (
    "invalid library", "TLS connect error", "SSL_ERROR", "tls connect error",
    "Proxy CONNECT", "ProxyError", "CONNECT aborted", "Failed to perform, curl: (56)",
    # Network interruption timeout（DDG/mail.tm Direct connection intermittent timeout）：reconstruction Session possible later
    # fall into different DNS parse/routing path，Avoid instantaneous inaccessibility
    "curl: (28)", "ConnectTimeout", "ReadTimeout", "FetchError",
)

class RetrySession(_CSession):
    def __init__(self, *args, **kwargs):
        self._init_args = args
        self._init_kwargs = kwargs
        super().__init__(*args, **kwargs)

    def request(self, method, url, *args, **kwargs):
        last = None
        for attempt in range(6):
            try:
                return super().request(method, url, *args, **kwargs)
            except Exception as e:
                msg = str(e)
                if any(h in msg for h in _RETRY_HINTS):
                    last = e
                    # Rebuild the ground floor curl handle：brand new Session Can bypass bad connections
                    try:
                        self.close()
                    except Exception:
                        pass
                    try:
                        self.__init__(*self._init_args, **self._init_kwargs)
                    except Exception:
                        pass
                    time.sleep(0.7 * (attempt + 1))
                    continue
                raise
        raise last

# External exposure and original curl_cffi consistent API
# key：let requests.Session also points to RetrySession，
# so chatgpt.py inside requests.Session(...) Automatically retry。
_creq.Session = RetrySession
requests = _creq
Session = RetrySession
