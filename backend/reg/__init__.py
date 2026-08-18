# -*- coding: utf-8 -*-
"""reg — OpenAI/ChatGPT Account registration function（Reproduced from mail-otp-server Register engine）

Core Registration Agreement（chatgpt_core.py）：Reuse codex_register-main of chatgpt.py Registration link
（next-auth signin → authorize → OTP → email-otp/validate → sentinel create_account
→ accessToken/session_token ending），sentinel t/so By pure Python VM generate
（sentinel_pure_vm.py），Email channel support mailtm / 163（IMAP，Credentials are injected into environment variables）。

Scheduling（engine.py）：event ring buffer + Polling interface（This front end has no SSE，3s Polling increment），
within thread stdout Forward as log event（Thread local，Does not pollute uvicorn log）。

Dropped into the library（repo_accounts.py）：Register Output Write reg_accounts surface（With password/Source email/channel），
The successful account is written into this project at the same time tokens surface（source=register），Can be used directly to lift the chain。
"""
from . import engine  # noqa: F401
from . import repo_accounts  # noqa: F401