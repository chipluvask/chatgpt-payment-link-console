"""
native_pow.py — Ghost in the Browser · direction A Reference implementation
========================================================
Put the verification side PoW WASM put in【Native WASM runtime】（wasmer / wasmtime / self-research），
within runtime【rewrite it import Browser host function】，and have these functions return true Chrome
Consistent environmental values ​​under the same claim image，Simultaneously driven by a high-precision clock ~16.6ms Render frame aggregation，
Alignment rAF / rIC timing side channel。

This is zero-browser The core of the solution：Does not start any browser engine，Only in native code"play"
browser host。What is running is the original version of the question WASM（black box），Replace only host imports，therefore
even WASM Forget about the reverse direction，And verify with the server 100% consistent。

rely（Choose one，Go by default demo model）：
  - pywasmer        : pip install wasmer wasmer_compiler_cranelift
  - wasmtime-py     : pip install wasmtime
  - pure Python demo  : No dependencies，Demonstration protocol packet only（host_sum Use the reference formula to calculate，Not true WASM）

Catch it before use PoW WASM Put in the same directory po.wasm（See README_solver.md）。
"""

from __future__ import annotations
import ctypes
import json
import math
import os
import struct
import time
from dataclasses import dataclass, field, asdict
from typing import Callable, Optional


# ----------------------------------------------------------------------------
# 1) Device portrait：with you TLS/JA4/UA Desktop browser portrait declared in【Must be self-consistent】
#    here with "Mid-range desktop Chrome" For example。If you want to change the portrait, change it here. + UA。
# ----------------------------------------------------------------------------
@dataclass
class BrowserProfile:
    hardware_concurrency: int = 8      # navigator.hardwareConcurrency
    device_memory: float = 8.0         # navigator.deviceMemory (GB)
    screen_width: int = 1920
    screen_height: int = 1080
    device_pixel_ratio: float = 1.0
    avail_width: int = 1920
    avail_height: int = 1040
    platform: str = "Win32"
    languages: list[str] = field(default_factory=lambda: ["en-US", "en"])
    max_touch_points: int = 0
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )


# 16.6ms ≈ 60fps render frame；rAF Nominal period of triggering rhythm（direction B Timing side channel alignment）
RAF_FRAME_MS = 1000.0 / 60.0
# rIC（requestIdleCallback）Nominal standard deviation of macrotask rhythm jitter（real Chrome Observation interval）
RIC_SIGMA_MS = 1.8


class VirtualTimeline:
    """Unified virtual time domain（respond gpt-5.6-sol C.1 / E.7 / E.8）。

    critical corrections：rAF is the rendering scheduling semantics，Not every 16.6ms the clock returned。previous edition
    'fixed seed LCG + reality sleep'Neither can replicate the causal semantics of frame scheduling，Fixed jitter instead
    Become a stronger fingerprint（C.2）。Use here instead：

      - internal time：Deterministic virtual clock，Called by/Event status advancement，Not casually true sleep，
        Meet the module's own consistency check；
      - Server visible time：Time consuming to only decide on demand whether you need to match a real wall clock before sending，
        Decoupled from internal time（E.8）。
    """
    # time origin fixed to 0，with browser performance.timeOrigin semantic alignment（Internal use only）
    def __init__(self, frame_ms: float = RAF_FRAME_MS, time_origin: float = 0.0):
        self.frame_ms = frame_ms
        self.time_origin = time_origin
        self._mono = time.perf_counter_ns() / 1_000_000.0  # true monotonic starting point
        self._virtual = time_origin                       # virtual present（ms）
        self.frame_index = 0
        # Frame advancement uses deterministic increments（Triangular wave throttling，Avoid fixing seeds into fingerprints）
        self._phase = 0

    def now(self) -> float:
        """performance.now() equivalence（virtual，ms）。"""
        return self._virtual - self.time_origin

    def wall_now(self) -> float:
        """real wall clock（ms，relatively mono starting point），Compare the visible time of the server when necessary。"""
        return time.perf_counter_ns() / 1_000_000.0 - self._mono

    def advance_computation(self, busy_ms: float):
        """Use truth busy-wait Advance internal virtual time，make'workload—time consuming'joint distribution real
        （respond C.4：Time associated with matching workload，rather than adding dither independently）。"""
        busy = max(0.0, busy_ms)
        # Measuring true busy wait with monotonic clocks，avoid OS False sleep caused by scheduling
        tgt = time.perf_counter_ns() + int(busy * 1_000_000)
        while time.perf_counter_ns() < tgt:
            pass
        self._virtual += busy

    def tick_frame(self) -> float:
        """advance one frame：Deterministic throttling of frame intervals over time（dropped frames/reply），simulation visible/Throttle，
        No naked reporting of fixed jitter to the server。Return the virtual delay of this frame(ms)。"""
        self.frame_index += 1
        self._phase = (self._phase + 1) % 7
        # triangle wave：manufactured in certain frames 0/± Jitter，embody visibility/Throttle，Instead of Gaussian fixed fingerprint
        jitter = (self._phase - 3) * 0.6  # -1.8 .. +1.8 ms cyclical changes
        self._virtual += max(0.0, self.frame_ms + jitter)
        return self.frame_ms + jitter

    @property
    def expected_frame(self) -> float:
        return self.frame_index * self.frame_ms


# ----------------------------------------------------------------------------
# 2) Native WASM runtime encapsulation
# ----------------------------------------------------------------------------
class NativePow:
    def __init__(self, profile: BrowserProfile, wasm_path: Optional[str] = None):
        self.profile = profile
        self.clock = VirtualTimeline()
        self.wasm_path = wasm_path or os.path.join(os.path.dirname(__file__), "po.wasm")
        self._backend = self._load_backend()

    # -- Backend selection -------------------------------------------------------------
    def _load_backend(self) -> str:
        try:
            import wasmer  # noqa: F401
            return "wasmer"
        except Exception:
            pass
        try:
            import wasmtime  # noqa: F401
            return "wasmtime"
        except Exception:
            pass
        if os.path.exists(self.wasm_path):
            # have WASM but no native binding：Prompt user to install
            print("[!] turn up po.wasm but not installed wasmer/wasmtime，please pip install wasmer wasmer_compiler_cranelift")
            return "stub"
        return "demo"

    # -- Browser host function import table（host imports）--------------------------------
    # This section is about"happy DOM hollow probe"Replace with true Chrome self-consistent truth value。
    def _host_imports(self) -> dict:
        p = self.profile
        clock = self.clock

        def now_ms() -> float:
            return clock.now()

        def hardware_concurrency() -> int:
            return p.hardware_concurrency

        def device_memory() -> float:
            return p.device_memory

        def screen_w() -> int:
            return p.screen_width

        def screen_h() -> int:
            return p.screen_height

        def avail_w() -> int:
            return p.avail_width

        def avail_h() -> int:
            return p.avail_height

        def dpr() -> float:
            return p.device_pixel_ratio

        def max_touch() -> int:
            return p.max_touch_points

        def platform_ptr() -> int:
            # In real implementation, you need to write the string into WASM Linear memory and return pointer；
            # Here is the contract，specific offset depending on WASM The exported memory layout of。
            raise NotImplementedError("platform String needs to be pressed WASM memory layout alignment；demo pattern ignore")

        # Counting probe——【DEMO ONLY，Never mix in the truth proof】（respond gpt-5.6-sol B.1）
        # reality WASM Internal has it's own weight/Hash，This placeholder formula cannot explain the 4778，
        # It is also impossible to predict the successful browser value；Real mode must be WASM The return value shall prevail。
        def aggregate_host_sum_demo() -> int:
            return (
                p.hardware_concurrency * 137
                + int(p.device_memory) * 53
                + p.screen_width // 10
                + p.screen_height // 10
                + p.max_touch_points * 7
            )

        return {
            "env": {
                "now": now_ms,
                "hardwareConcurrency": hardware_concurrency,
                "deviceMemory": device_memory,
                "screenWidth": screen_w,
                "screenHeight": screen_h,
                "availWidth": avail_w,
                "availHeight": avail_h,
                "devicePixelRatio": dpr,
                "maxTouchPoints": max_touch,
                "platform": platform_ptr,
                "aggregateHostSum_DEMO_ONLY": aggregate_host_sum_demo,
                # random number：Pure protocol determinability（with portrait/salt binding），Easy to reproduce
                "randomU32": lambda: (int(clock.now() * 1000) ^ 0x5BD1E995) & 0xFFFFFFFF,
            }
        }

    # -- Really count token --------------------------------------------------------
    def solve(self, challenge: dict) -> dict:
        """challenge Contains at least {n, salt}（press true endpoint Field adjustment）。"""
        if self._backend == "demo":
            return self._demo_solve(challenge)
        # real backend（wasmer/wasmtime）Load and call WASM of solve Export，
        # Bundle host imports injection。Export name is true WASM Adjustment。
        return self._real_solve(challenge)

    def _real_solve(self, challenge: dict) -> dict:
        # —— first step：static analysis true ABI，Never guess the name（gpt-5.6-sol A.6 / E.2）——
        try:
            from wasm_abi import analyze as wasm_analyze
            abi = wasm_analyze(self.wasm_path)
        except Exception as e:
            abi = None
            print(f"[!] Unable to statically parse ABI（will try to minimize hook）: {e}")
        if abi is not None:
            print(f"[abi] import function = {[f'{i.module}.{i.field}' for i in abi.imports if i.kind=='func']}")
            print(f"[abi] export     = {[f'{e.name}' for e in abi.exports]}")
            # A.1：like import There are no environmental probes at all，The description of the image data is provided by JS write memory，
            # The route should be changed to recurring input buffer rather than hook these names import。
            probe_names = {"hardwareConcurrency", "deviceMemory", "screenWidth"}
            has_probe_imports = any(
                i.field in probe_names for i in abi.imports if i.kind == "func"
            )
            if not has_probe_imports:
                print("[abi] ⚠ Environment probe not detected import —— The data is likely to be composed of JS loader "
                      "write linear memory（A.1）。Please use instead wasm_abi Positioning data entry。")
            # E.6：only hook real import name；unknown import Explicit error reporting，Return without silence 0
            real_import_fields = {i.field for i in abi.imports}
        else:
            real_import_fields = set()

        if self._backend == "wasmer":
            import wasmer
            store = wasmer.Store()
            with open(self.wasm_path, "rb") as f:
                module = wasmer.Module(store, f.read())
            import_object = wasmer.ImportObject()
            for mod, fns in self._host_imports().items():
                for name, fn in fns.items():
                    # name shaped like aggregateHostSum_DEMO_ONLY：Real mode does not inject demo Placeholder
                    if name.endswith("_DEMO_ONLY"):
                        continue
                    # E.6：If static analysis exists and the original name is not real import surface，Skip explicitly instead of returning silently 0
                    if real_import_fields and name not in real_import_fields:
                        continue
                    import_object.register(mod, {name: fn})
            instance = wasmer.Instance(module, import_object)
            # Alignment rendering frame rhythm（virtual time advance，No naked reporting of fixed jitter）：before calling trunk/Advance by frame
            for _ in range(challenge.get("frames", 1)):
                self.clock.tick_frame()
            # call true export：priority ABI The parsed export name（A.6 Correction）
            export_names = [e.name for e in (abi.exports if abi else [])]
            if not export_names:
                export_names = ["solve", "mint", "compute", "pow"]  # reveal all the details
            last_err = None
            for export in export_names:
                if hasattr(instance.exports, export):
                    try:
                        result = getattr(instance.exports, export)(
                            challenge["n"], challenge.get("salt", b"")
                        )
                        return self._wrap_token(result, challenge)
                    except Exception as e:  # trap/ABI mistake：Position first，Pretend to succeed without swallowing（E.10）
                        last_err = e
                        # E.6：unknown import trigger trap Don't fake it 0，save scene
                        raise RuntimeError(
                            f"WASM Export {export} call failed（trap/ABI）：{e} —— "
                            f"Check first wasm_abi Missing positioning import memory/Calling sequence"
                        ) from e
            if last_err:
                raise last_err
            raise RuntimeError("WASM No available export found；Please compare wasm_abi Output adjustment")
        # wasmtime Branch slightly（Same structure），Prompt users to refer to wasmer Branch implementation
        raise NotImplementedError("wasmtime Please refer to the branch wasmer accomplish ImportObject mapping")

    def _wrap_token(self, raw, challenge: dict) -> dict:
        """Bundle WASM The return value is sealed as expected by the verification interface. proof token Bag。

        host_sum must come from WASM Internal real return value（The location needs to go through wasm_abi E.3 position），
        Never use demo Placeholder formula。
        """
        # raw may be int（Single return value）or an object with properties；host_sum Fetched from the correct location by the caller
        token = {
            "n": challenge.get("n"),
            "salt": challenge.get("salt"),
            "host_sum": getattr(raw, "host_sum", None),
            "timing": {
                "frame_index": self.clock.frame_index,
                "expected_ms": round(self.clock.expected_frame, 2),
                "virtual_now_ms": round(self.clock.now(), 3),
            },
            "profile": asdict(self.profile),
        }
        return token

    # -- demo model：none WASM / When there is no native binding，Demo protocol packet ----------------
    def _demo_solve(self, challenge: dict) -> dict:
        print("[demo] real not loaded po.wasm —— Demonstration protocol packet only；host_sum for DEMO Placeholder，"
              "Never substitute reality proof（gpt-5.6-sol B.1）")
        p = self.profile
        # DEMO Placeholder：For illustration only“If there really is an environment accumulation channel，host_sum Should be bound to the image”。
        # The true value must come from WASM return value（through wasm_abi E.3 position），and 4778 more likely
        # failure sentinel/Initialize checksum，rather than environmental accumulation（gpt-5.6-sol D.4）。
        host_sum = (
            p.hardware_concurrency * 137
            + int(p.device_memory) * 53
            + p.screen_width // 10
            + p.screen_height // 10
            + p.max_touch_points * 7
        )
        # Frame advancing through the virtual timeline（No naked reporting of fixed jitter；C.1/C.2）
        frames = challenge.get("frames", 8)
        deltas = []
        for _ in range(frames):
            deltas.append(self.clock.tick_frame())
        token = {
            "n": challenge.get("n"),
            "salt": challenge.get("salt"),
            "host_sum": host_sum,
            "timing": {
                "frames": frames,
                "mean_frame_ms": round(sum(deltas) / len(deltas), 3),
                "std_ms": round(self._std(deltas), 3),
                "expected_ms": round(self.clock.expected_frame, 2),
                "virtual_now_ms": round(self.clock.now(), 3),
            },
            "profile": asdict(self.profile),
        }
        print(f"[demo] host_sum(Placeholder)={host_sum}  mean_frame={token['timing']['mean_frame_ms']}ms "
              f"(question VM dead value 4778 may be sentinel，Accumulation of non-empty environments)")
        return token

    @staticmethod
    def _std(xs):
        n = len(xs)
        if n < 2:
            return 0.0
        m = sum(xs) / n
        return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


if __name__ == "__main__":
    rt = NativePow(BrowserProfile())
    out = rt.solve({"n": 1, "salt": b"passive", "frames": 8})
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
