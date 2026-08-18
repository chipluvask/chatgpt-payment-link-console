# Pre-run checklist（README_solver）

> The current desktop environment only has the question surface，No `passive_bridge.py` / `profile_ab.json` / `node_bridge.js`，
> There is also no validation endpoint with PoW WASM。to really run out `flag`，Click below to complete。

## 1. Two things you need to complete
1. **PoW WASM**（`po.wasm`）：Open the bill authorization portal in a real browser，At Network/Application panel
   Grab the verifier loaded in PoW WASM byte，deposit to `solver/po.wasm`。
   - Also available happy-dom exist passive The same copy captured when the pattern was loaded（It's the wrong one）。
2. **Authentication endpoint + your authorization session**：
   - `PASSIVE_CHALLENGE_URL`：Server-side delivery passive Challenge interface（Usually something like `.../checks/challenge`）。
   - `PASSIVE_SUBMIT_URL`：submit proof token interface（in the title"Authentication interface"）。
   - `AUTH_COOKIE`：session of your authorized account cookie（Test environment for zero amount verification）。
   - These are in the attachment to the title `passive_bridge.py` Here is"Conquered"protocol layer，Just reuse it directly。

## 2. Install native WASM runtime（Choose one）
- wasmer（recommend）：`pip install wasmer wasmer_compiler_cranelift`
- or wasmtime：`pip install wasmtime`

  When there is no native binding，`native_pow.py` will enter **demo model**，Only demonstrates protocol packets and
  `host_sum≠4778` The main points，**Can't really run WASM，It won't be true token**。

## 3. Align device images
`native_pow.py` top `BrowserProfile` that is you"claim"desktop Chrome portrait。
it must be related to：
- You are TLS/JA4 + `User-Agent` The device declared in，
- as well as `wasm-objdump -j import` seen WASM reality import name

**All self-consistent**。inconsistent → Timing/The image second-level verification will still soft-reject。

## 4. run
```bash
cd solver
pip install wasmer wasmer_compiler_cranelift   # or wasmtime
export CTF_AUTH_COOKIE="<your authorization session>"
export CTF_CHALLENGE_URL="https://<gateway>/checks/challenge"
export CTF_SUBMIT_URL="https://<gateway>/checks"
python run_solver.py
```
successful output：
```
[✓] success=true
    token  = <VALID_TOKEN>
    flag   = flag{<base64(token)>}
```
`flag.txt` can also write，Just submit it directly。

## 5. Troubleshooting
- `host_sum` still = 4778 or fall on VM interval → WASM of host import The mapping is not correct，
  use `wasm-objdump -j import po.wasm` control `native_pow._host_imports` The key names are aligned one by one。
- `success=false` but `host_sum` Already normal → timing side channel：increase `RenderClock.frames`、
  calibration `RAF_FRAME_MS`（Different refresh rates are not 16.6）、or let `std_ms` Come true Chrome Observation interval。
- Want to verify quickly"Native replacement happy-dom"equivalence of，Run first `python native_pow.py` look demo output。

## 6. Compliance reminder
Only if you have your own authorized account + Run the zero amount verification test endpoint declared in the question。Not for unauthorized access or fraud。
