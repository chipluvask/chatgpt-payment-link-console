// sentinel_bootstrap.js — Loading true·sdk.js Prepare the browser environment before shim。
// Only available sdk.js The object that will actually be read/method，value alignment Edge 150 / zh-CN。
(function () {
  "use strict";
  var g = globalThis;

  // sdk inside“Self-tamper proof”The trap will run catastrophic backtracking rules on the function source code (((.+)+)+)+$。
  // real browser V8 Hit instantly；goja/regexp2 Will get stuck exponentially。Here is a short circuit to the fixed mode，
  // Returns results consistent with real browsers（A non-empty string must hit→return 0），does not affect token calculate。
  var _search = String.prototype.search;
  String.prototype.search = function (re) {
    try {
      var s = (re && re.source) ? re.source : String(re);
      if (s.indexOf("(((.+)+)+)+") !== -1) return this.length ? 0 : -1;
    } catch (e) {}
    return _search.call(this, re);
  };

  // goja throw TypeError Use old wording "Cannot read property 'x' of undefined/null"，
  // V8/Chrome use "Cannot read properties of undefined/null (reading 'x')"。
  // collector will visit undefined Error strings when attributes are recorded as fingerprint entropy（like clientBootstrap），
  // Inconsistent phrasing will expose the non- V8 engine。overwrite Error.toString Bundle goja The copy is rewritten as V8 copywriting。
  var _errToString = Error.prototype.toString;
  Error.prototype.toString = function () {
    var s = _errToString.call(this);
    try {
      s = s.replace(/Cannot read property '([^']*)' of undefined/g, "Cannot read properties of undefined (reading '$1')")
           .replace(/Cannot read property '([^']*)' of null/g, "Cannot read properties of null (reading '$1')");
    } catch (e) {}
    return s;
  };

  // sdk based on setInterval Anti-debugging polling（Check every few seconds debugger）。
  // exist eventloop Setting this loop timer will make the event loop never clear → loop stuck。
  // Disposable token Calculation does not require it，Leave it blank directly；setTimeout reserve（dx VM Will use）。
  g.setInterval = function () { return 0; };
  g.clearInterval = function () {};

  // crypto.getRandomValues（uuid v4 generate sentinel deviceId when needed）
  g.crypto = g.crypto || {};
  if (typeof g.crypto.getRandomValues !== "function") {
    g.crypto.getRandomValues = function (arr) {
      for (var i = 0; i < arr.length; i++) arr[i] = (Math.random() * 256) | 0;
      return arr;
    };
  }
  if (typeof g.crypto.randomUUID !== "function") {
    g.crypto.randomUUID = function () {
      var b = new Uint8Array(16);
      g.crypto.getRandomValues(b);
      b[6] = (b[6] & 0x0f) | 0x40;
      b[8] = (b[8] & 0x3f) | 0x80;
      var h = [];
      for (var i = 0; i < 16; i++) h.push((b[i] + 0x100).toString(16).slice(1));
      return h[0] + h[1] + h[2] + h[3] + "-" + h[4] + h[5] + "-" + h[6] + h[7] +
        "-" + h[8] + h[9] + "-" + h[10] + h[11] + h[12] + h[13] + h[14] + h[15];
    };
  }

  // window / self self-reference
  g.window = g;
  g.self = g;
  g.top = g;
  g.parent = g;

  // ---- Date overwrite：Outputs the time zone consistent with the current exporting country ----
  var _DateToString = Date.prototype.toString;
  Date.prototype.toString = function () {
    try {
      var timezone = g.__TIMEZONE__ || "America/Chicago";
      var source = new Date(this.getTime());
      var parts = new Intl.DateTimeFormat("en-US", {
        timeZone: timezone,
        year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", second: "2-digit",
        hourCycle: "h23"
      }).formatToParts(source).reduce(function (out, part) {
        if (part.type !== "literal") out[part.type] = Number(part.value);
        return out;
      }, {});
      var localAsUtc = Date.UTC(
        parts.year, parts.month - 1, parts.day,
        parts.hour, parts.minute, parts.second
      );
      var offsetMinutes = Math.round((localAsUtc - source.getTime()) / 60000);
      var d = new Date(source.getTime() + offsetMinutes * 60000);
      var wd = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][d.getUTCDay()];
      var mo = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][d.getUTCMonth()];
      function p(n) { return (n < 10 ? "0" : "") + n; }
      var sign = offsetMinutes >= 0 ? "+" : "-";
      var offset = Math.abs(offsetMinutes);
      return wd + " " + mo + " " + p(d.getUTCDate()) + " " + d.getUTCFullYear() +
        " " + p(d.getUTCHours()) + ":" + p(d.getUTCMinutes()) + ":" + p(d.getUTCSeconds()) +
        " GMT" + sign + p(Math.floor(offset / 60)) + p(offset % 60) + " (" + timezone + ")";
    } catch (e) {
      return _DateToString.call(this);
    }
  };

  // ---- Construct native method：toString() return "function name() { [native code] }" ----
  function nativeFn(name) {
    var f = function () {};
    try { Object.defineProperty(f, "name", { value: name, configurable: true }); } catch (e) {}
    f.toString = function () { return "function " + name + "() { [native code] }"; };
    return f;
  }

  // Navigator prototype：a batch Chromium/Edge 150 the real way + several properties getter。
  var navProtoMethods = [
    "clearOriginJoinedAdInterestGroups", "joinAdInterestGroup", "leaveAdInterestGroup",
    "runAdAuction", "createAuctionNonce", "deprecatedReplaceInURN", "deprecatedURNToURL",
    "updateAdInterestGroups", "canShare", "share", "requestMIDIAccess",
    "requestMediaKeySystemAccess", "getGamepads", "getBattery", "sendBeacon", "vibrate",
    "registerProtocolHandler", "unregisterProtocolHandler", "setAppBadge", "clearAppBadge",
    "getInstalledRelatedApps", "javaEnabled", "taintEnabled", "getUserMedia",
    "webkitGetUserMedia"
  ];
  var NavigatorProto = {};
  navProtoMethods.forEach(function (m) { NavigatorProto[m] = nativeFn(m); });
  // few attributes(some Tt() Returns the string form of its value on a random hit)
  NavigatorProto.cookieEnabled = true;
  NavigatorProto.onLine = true;
  NavigatorProto.pdfViewerEnabled = true;
  NavigatorProto.webdriver = false;

  var navigator = Object.create(NavigatorProto);
  navigator.userAgent = g.__UA__;
  navigator.appVersion = g.__UA__.replace("Mozilla/", "");
  navigator.appName = "Netscape";
  navigator.appCodeName = "Mozilla";
  navigator.platform = "Win32";
  navigator.product = "Gecko";
  navigator.productSub = "20030107";
  navigator.vendor = "Google Inc.";
  navigator.vendorSub = "";
  navigator.language = g.__LANGUAGE__ || "en-US";
  navigator.languages = g.__LANGUAGES__ || [navigator.language, "en-US", "en"];
  navigator.hardwareConcurrency = g.__CORES__;
  navigator.deviceMemory = 8;
  navigator.maxTouchPoints = 0;
  navigator.doNotTrack = null;
  // common WebAPI sub-object (collector_dx Will detect)
  var noop = function () {};
  var noopPromise = function () { return Promise.resolve(); };
  navigator.connection = { effectiveType: "4g", rtt: 50, downlink: 10, saveData: false, type: "wifi" };
  navigator.plugins = { length: 5, item: noop, namedItem: noop, refresh: noop };
  navigator.mimeTypes = { length: 4, item: noop, namedItem: noop };
  navigator.permissions = { query: function () { return Promise.resolve({ state: "prompt" }); } };
  navigator.mediaDevices = { enumerateDevices: function () { return Promise.resolve([]); }, getUserMedia: noopPromise };
  navigator.credentials = { get: noopPromise, store: noopPromise, create: noopPromise, preventSilentAccess: noopPromise };
  navigator.serviceWorker = { controller: null, ready: Promise.resolve({ active: null }), register: noopPromise, getRegistrations: function () { return Promise.resolve([]); } };
  navigator.storage = { estimate: function () { return Promise.resolve({ quota: 2e11, usage: 5e7 }); }, getDirectory: noopPromise, persisted: function () { return Promise.resolve(false); }, persist: function () { return Promise.resolve(false); } };
  navigator.clipboard = { read: noopPromise, readText: noopPromise, write: noopPromise, writeText: noopPromise };
  navigator.locks = { request: noopPromise, query: function () { return Promise.resolve({ held: [], pending: [] }); } };
  navigator.mediaCapabilities = { decodingInfo: function () { return Promise.resolve({ supported: true, smooth: true, powerEfficient: true }); } };
  navigator.userAgentData = { brands: [{ brand: "Google Chrome", version: "136" }, { brand: "Chromium", version: "136" }, { brand: "Not.A/Brand", version: "99" }], mobile: false, platform: "Windows", getHighEntropyValues: function () { return Promise.resolve({}); } };
  navigator.scheduling = { isInputPending: function () { return false; } };
  navigator.ink = { requestPresenter: noopPromise };
  navigator.gpu = { requestAdapter: noopPromise };
  navigator.hid = { getDevices: function () { return Promise.resolve([]); }, requestDevice: noopPromise };
  navigator.serial = { getPorts: function () { return Promise.resolve([]); }, requestPort: noopPromise };
  navigator.usb = { getDevices: function () { return Promise.resolve([]); }, requestDevice: noopPromise };
  navigator.bluetooth = { getAvailability: function () { return Promise.resolve(false); }, requestDevice: noopPromise };
  navigator.xr = { isSessionSupported: function () { return Promise.resolve(false); }, requestSession: noopPromise };
  navigator.wakeLock = { request: noopPromise };
  navigator.geolocation = { getCurrentPosition: noop, watchPosition: noop, clearWatch: noop };
  navigator.mediaSession = { metadata: null, playbackState: "none", setActionHandler: noop };
  g.navigator = navigator;

  // ---- screen ----
  g.screen = {
    width: 1920, height: 1080, availWidth: 1920, availHeight: 1032,
    colorDepth: 24, pixelDepth: 24, availLeft: 0, availTop: 0
  };
  g.innerWidth = 1920; g.innerHeight = 945;
  g.outerWidth = 1920; g.outerHeight = 1032;
  g.devicePixelRatio = 1;

  // ---- history / location ----
  // collector The current page will be recorded URL as fingerprint entropy。The real registration flow is at /about-you page trigger create_account
  // of sentinel；Go side available __PAGE_URL__ by specific flow overwrite，Default alignment about-you。
  g.history = { length: 2, scrollRestoration: "auto", state: null };
  var _pageUrl = g.__PAGE_URL__ || "https://auth.openai.com/about-you";
  var _parsedPageUrl = new URL(_pageUrl);
  g.location = {
    href: _pageUrl, origin: _parsedPageUrl.origin,
    protocol: _parsedPageUrl.protocol, host: _parsedPageUrl.host, hostname: _parsedPageUrl.hostname,
    port: _parsedPageUrl.port, pathname: _parsedPageUrl.pathname,
    search: _parsedPageUrl.search, hash: _parsedPageUrl.hash,
    assign: function () {}, replace: function () {}, reload: function () {}, toString: function () { return _pageUrl; }
  };

  // ---- performance ----
  // collector Can read navigation performance entries name（= Current page URL）as fingerprint entropy，The real page is produced here
  // "https://auth.openai.com/about-you"。lack getEntriesByType The measuring point is empty when → One item missing。
  var _t0 = Date.now();
  var _navEntry = {
    name: _pageUrl, entryType: "navigation", startTime: 0, duration: 420.5, type: "navigate",
    initiatorType: "navigation", nextHopProtocol: "h2", redirectCount: 0,
    domComplete: 410.2, domContentLoadedEventEnd: 300.1, domInteractive: 280.4,
    loadEventEnd: 418.9, responseEnd: 190.3, responseStart: 150.7, requestStart: 60.2,
    fetchStart: 5.1, connectEnd: 40.8, connectStart: 20.3, domainLookupEnd: 15.2,
    domainLookupStart: 10.1, secureConnectionStart: 25.6, transferSize: 18240, encodedBodySize: 17010, decodedBodySize: 61200
  };
  g.performance = {
    timeOrigin: _t0,
    now: function () { return (Date.now() - _t0) + Math.random(); },
    memory: { jsHeapSizeLimit: 4294705152, totalJSHeapSize: 35000000, usedJSHeapSize: 22000000 },
    getEntries: function () { return [_navEntry]; },
    getEntriesByType: function (t) { return t === "navigation" ? [_navEntry] : []; },
    getEntriesByName: function (n) { return _navEntry.name === n ? [_navEntry] : []; },
    mark: function () {}, measure: function () {}, clearMarks: function () {}, clearMeasures: function () {},
    clearResourceTimings: function () {}, setResourceTimingBufferSize: function () {}
  };

  // ---- localStorage ----
  // collector_dx Will enumerate Object.keys(localStorage) as fingerprint entropy。reality auth Page at
  // statsig client SDK After initialization, a batch of statsig.* key；goja The environment should not be SDK，
  // These keys need to be preset according to the real structure，And the method must be non-enumerable，otherwise keys Method names will be enumerated。
  (function () {
    function digits(n) { var s = ""; for (var i = 0; i < n; i++) s += (Math.random() * 10) | 0; if (s[0] === "0") s = "1" + s.slice(1); return s; }
    function hex(n) { var h = "0123456789abcdef", s = ""; for (var i = 0; i < n; i++) s += h[(Math.random() * 16) | 0]; return s; }
    var stable = digits(9);
    var ls = {};
    var seed = [
      "statsig.cached.evaluations." + digits(8),
      "statsig.cached.evaluations." + digits(9),
      "statsig.cached.evaluations." + digits(10),
      "statsig.last_modified_time.evaluations",
      hex(16),
      "statsig.cached.evaluations." + digits(10),
      "statsig.session_id." + stable,
      "statsig.cached.evaluations." + digits(10),
      "statsig.cached.evaluations." + digits(10),
      "statsig.cached.evaluations." + digits(10),
      "statsig.stable_id." + stable
    ];
    seed.forEach(function (k) { ls[k] = "1"; });
    if (g.__SEED_DID_KEY__ && g.__SEED_DID_VAL__) ls[g.__SEED_DID_KEY__] = g.__SEED_DID_VAL__;
    function def(name, fn) { Object.defineProperty(ls, name, { value: fn, enumerable: false, writable: true, configurable: true }); }
    def("getItem", function (k) { return Object.prototype.hasOwnProperty.call(ls, k) ? ls[k] : null; });
    def("setItem", function (k, v) { ls[k] = "" + v; });
    def("removeItem", function (k) { delete ls[k]; });
    def("clear", function () { Object.keys(ls).forEach(function (k) { delete ls[k]; }); });
    def("key", function (i) { return Object.keys(ls)[i] || null; });
    Object.defineProperty(ls, "length", { get: function () { return Object.keys(ls).length; }, enumerable: false, configurable: true });
    g.localStorage = ls;
  })();

  // ---- document（sdk read scripts / documentElement / cookie / keys / body Text measurement fingerprint）----
  var sdkScript = { src: g.__SDK_URL__, getAttribute: function () { return null; }, type: "text/javascript" };
  var docElement = { getAttribute: function () { return null; }, tagName: "HTML", lang: g.__LANGUAGE__ || "en-US" };
  var _cookie = g.__COOKIE_HEADER__ || ((g.__SEED_DID_KEY__ && g.__SEED_DID_VAL__) ? (g.__SEED_DID_KEY__ + "=" + g.__SEED_DID_VAL__) : "");

  // writable style shell：collector The text fingerprint will Reflect.set(style, "fontFamily"/"fontSize"/... )
  function makeStyle() {
    var st = {};
    st.setProperty = function (k, v) { st[k] = "" + v; };
    st.getPropertyValue = function (k) { return Object.prototype.hasOwnProperty.call(st, k) ? st[k] : ""; };
    st.removeProperty = function (k) { var v = st[k]; delete st[k]; return v; };
    st.cssText = "";
    return st;
  }

  // DOM elemental shell：createElement("div") Metadata style/innerText，appendChild arrive body，
  // Again getBoundingClientRect()（The result will be JSON.stringify），at last removeChild。
  function makeElement(tag) {
    var el = {
      tagName: ("" + tag).toUpperCase(),
      nodeName: ("" + tag).toUpperCase(),
      nodeType: 1,
      style: makeStyle(),
      innerText: "", textContent: "", innerHTML: "",
      className: "", id: "", ariaHidden: null, hidden: false,
      clientWidth: 0, clientHeight: 0, offsetWidth: 0, offsetHeight: 0,
      scrollWidth: 0, scrollHeight: 0, offsetLeft: 0, offsetTop: 0,
      children: [], childNodes: [], parentNode: null,
      setAttribute: function () {}, getAttribute: function () { return null; },
      removeAttribute: function () {}, hasAttribute: function () { return false; },
      addEventListener: function () {}, removeEventListener: function () {},
      appendChild: function (c) { this.children.push(c); this.childNodes.push(c); if (c) c.parentNode = this; return c; },
      removeChild: function (c) {
        var i = this.children.indexOf(c);
        if (i >= 0) { this.children.splice(i, 1); this.childNodes.splice(i, 1); }
        if (c) c.parentNode = null;
        return c;
      },
      insertBefore: function (c) { this.children.push(c); this.childNodes.push(c); return c; },
      remove: function () {},
      querySelector: function () { return null; },
      querySelectorAll: function () { return []; },
      getClientRects: function () { return [this.getBoundingClientRect()]; },
      getBoundingClientRect: function () {
        // No real layout：Gives stable sub-pixel width by text length（Impact 15px approximate），
        // The result is only recorded by the server as fingerprint entropy。
        var t = "" + (this.innerText || "");
        var w = t.length ? (t.length * 7.34 + 0.421875) : 0;
        var h = t.length ? 17.5 : 0;
        return { x: 8, y: 8, width: w, height: h, top: 8, right: 8 + w, bottom: 8 + h, left: 8 };
      }
    };
    return el;
  }

  var bodyEl = makeElement("body");
  var headEl = makeElement("head");
  g.document = {
    scripts: [sdkScript],
    documentElement: docElement,
    body: bodyEl,
    head: headEl,
    getElementsByTagName: function (t) {
      t = String(t).toLowerCase();
      if (t === "script") return [sdkScript];
      if (t === "body") return [bodyEl];
      if (t === "head") return [headEl];
      return [];
    },
    getElementById: function () { return null; },
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    createElement: function (tag) { return makeElement(tag || "div"); },
    createTextNode: function (t) { return { nodeType: 3, textContent: "" + t }; },
    referrer: "",
    location: g.location,
    URL: _pageUrl,
    documentURI: _pageUrl,
    baseURI: _pageUrl,
    title: "",
    readyState: "complete",
    hidden: false,
    visibilityState: "visible",
    characterSet: "UTF-8",
    contentType: "text/html",
    get cookie() { return _cookie; },
    set cookie(v) { _cookie = "" + v; }
  };

  // ---- __reactRouterContext ----
  // collector meeting try-read ctx.state.loaderData.root.clientBootstrap Geography field。
  // reality auth Registration page here root for undefined，Reading its attributes will throw a chain of errors and be recorded as fingerprint entropy。
  // Keep root Missing（Same form as reality、Number of same measuring points），Error copy from above Error.toString
  // Overwrite and change uniformly to V8 phrasing，Avoid exposure to non- V8 engine。
  g.__reactRouterContext = { state: { loaderData: {} } };

  // ---- requestIdleCallback Keep undefined → sdk Walk setTimeout reveal all the details ----
  // ---- Common empty shells，avoid sdk Occasional access error ----
  g.addEventListener = function () {};
  g.removeEventListener = function () {};
  g.dispatchEvent = function () { return true; };
  g.matchMedia = function () { return { matches: false, addListener: function () {}, removeListener: function () {}, addEventListener: function () {}, removeEventListener: function () {} }; };
  if (typeof g.console === "undefined") g.console = { log: function () {}, warn: function () {}, error: function () {} };

  // ---- More collector_dx Common detection objects ----
  g.chrome = { runtime: { id: undefined, connect: function () {}, sendMessage: function () {} }, csi: function () { return {}; }, loadTimes: function () { return {}; } };
  g.caches = { open: function () { return Promise.resolve({ match: function () { return Promise.resolve(); } }); }, keys: function () { return Promise.resolve([]); }, has: function () { return Promise.resolve(false); }, match: function () { return Promise.resolve(); } };
  g.indexedDB = { open: function () { return { result: null, onerror: null, onsuccess: null }; }, databases: function () { return Promise.resolve([]); } };
  g.speechSynthesis = { getVoices: function () { return []; }, speak: function () {}, cancel: function () {}, pause: function () {}, resume: function () {} };
  g.visualViewport = { width: 1920, height: 945, offsetLeft: 0, offsetTop: 0, scale: 1, pageLeft: 0, pageTop: 0, addEventListener: function () {} };
  g.origin = "https://auth.openai.com";
  g.isSecureContext = true;
  g.crossOriginIsolated = false;
  g.originAgentCluster = false;
  g.credentialless = false;
  g.scheduler = { postTask: function (fn) { return Promise.resolve(fn()); } };
  g.trustedTypes = { createPolicy: function () { return { createHTML: function (s) { return s; } }; } };
  g.cookieStore = { get: function () { return Promise.resolve(null); }, getAll: function () { return Promise.resolve([]); }, set: function () { return Promise.resolve(); } };
  g.AbortController = function () { this.signal = { aborted: false }; this.abort = function () { this.signal.aborted = true; }; };
  g.AbortSignal = { abort: function () { return { aborted: true }; }, timeout: function () { return { aborted: false }; } };
  g.URL = g.URL || function (u) { this.href = u; this.toString = function () { return u; }; };
  g.URLSearchParams = g.URLSearchParams || function () { this.get = function () { return null; }; this.set = function () {}; this.toString = function () { return ""; }; };
  g.Blob = g.Blob || function () { this.size = 0; this.type = ""; };
  g.File = g.File || function () { this.name = ""; this.size = 0; };
  g.FileReader = g.FileReader || function () { this.readAsText = function () {}; this.readAsArrayBuffer = function () {}; };
  g.FormData = g.FormData || function () { this.append = function () {}; this.get = function () { return null; }; };
  g.Headers = g.Headers || function () { this.get = function () { return null; }; this.set = function () {}; };
  g.Request = g.Request || function (u) { this.url = u; this.method = "GET"; };
  g.Response = g.Response || function () { this.ok = true; this.status = 200; this.json = function () { return Promise.resolve({}); }; };
  g.MutationObserver = g.MutationObserver || function () { this.observe = function () {}; this.disconnect = function () {}; this.takeRecords = function () { return []; }; };
  g.IntersectionObserver = g.IntersectionObserver || function () { this.observe = function () {}; this.disconnect = function () {}; this.unobserve = function () {}; };
  g.ResizeObserver = g.ResizeObserver || function () { this.observe = function () {}; this.disconnect = function () {}; this.unobserve = function () {}; };
  g.PerformanceObserver = g.PerformanceObserver || function () { this.observe = function () {}; this.disconnect = function () {}; };
  g.MessageChannel = g.MessageChannel || function () { this.port1 = { postMessage: function () {}, onmessage: null }; this.port2 = { postMessage: function () {}, onmessage: null }; };
  g.BroadcastChannel = g.BroadcastChannel || function () { this.postMessage = function () {}; this.close = function () {}; };
  g.Worker = g.Worker || function () { this.postMessage = function () {}; this.terminate = function () {}; };
  g.SharedWorker = g.SharedWorker || function () { this.port = { postMessage: function () {} }; };
  g.WebSocket = g.WebSocket || function () { this.send = function () {}; this.close = function () {}; this.readyState = 3; };
  g.XMLHttpRequest = g.XMLHttpRequest || function () { this.open = function () {}; this.send = function () {}; this.setRequestHeader = function () {}; this.status = 0; this.responseText = ""; };
  g.Image = g.Image || function () { this.src = ""; this.onload = null; this.onerror = null; };
  g.HTMLElement = g.HTMLElement || function () {};
  g.HTMLDocument = g.HTMLDocument || function () {};
  g.Event = g.Event || function (t) { this.type = t; this.bubbles = false; this.cancelable = false; };
  g.CustomEvent = g.CustomEvent || function (t) { this.type = t; this.detail = null; };
  g.DOMParser = g.DOMParser || function () { this.parseFromString = function () { return { documentElement: g.document.documentElement }; }; };
  g.getComputedStyle = g.getComputedStyle || function () { return { getPropertyValue: function () { return ""; } }; };
  g.requestAnimationFrame = g.requestAnimationFrame || function (fn) { return setTimeout(fn, 16); };
  g.cancelAnimationFrame = g.cancelAnimationFrame || function (id) { clearTimeout(id); };
  g.queueMicrotask = g.queueMicrotask || function (fn) { Promise.resolve().then(fn); };
  g.structuredClone = g.structuredClone || function (v) { return JSON.parse(JSON.stringify(v)); };

  // ---- __oai_so_*：Session Behavior Telemetry Accumulator ----
  // create_account need second one sentinel head openai-sentinel-so-token，Its content is provided by
  // /sentinel/req inside so.collector_dx + so.snapshot_dx two paragraphs DX The program reads a batch of
  // window.__oai_so_* Accumulator calculates（real page passed keydown/pointermove/click/scroll/
  // wheel Event listener real-time accumulation）。Protocol mode has no real events，Click here“People are here about-you page stay
  // ~8 Second、Enter name+Birthday、Move mouse、Click”Preset self-consistent human behavior values，ensure collector
  // Not read undefined And the output structure is complete so-token。
  (function () {
    var nowP = (g.performance && g.performance.now) ? g.performance.now() : 1500;
    var t0 = nowP - 8085.5;              // Page into collection approx. 8 Second
    // keydown sequence of events（Enter name "Anna Wilson" + Birthday ~ 12 key press）
    var kd = [];
    var keys = ["A","n","n","a"," ","W","i","l","s","o","n","2"];
    var kt = t0 + 1200;
    for (var i = 0; i < keys.length; i++) {
      kt += 140 + Math.random() * 90;
      kd.push({ ctrlKey: false, metaKey: false, altKey: false, shiftKey: (i === 0 || i === 5), key: keys[i], type: "keydown", t: kt });
    }
    // pointermove sequence of events（mouse movement，Cumulative path length）
    var pm = [];
    var px = 640, py = 360, pt = t0 + 300, htot = 0, pcnt = 0;
    for (var j = 0; j < 30; j++) {
      var dx = (Math.random() - 0.5) * 40, dy = (Math.random() - 0.5) * 30;
      px += dx; py += dy; pt += 60 + Math.random() * 80;
      htot += Math.hypot(dx, dy); pcnt++;
      pm.push({ clientX: Math.round(px), clientY: Math.round(py), type: "pointermove", t: pt });
    }
    g.__oai_so_t0 = t0;
    g.__oai_so_h = kd;          // keydown event array
    g.__oai_so_hi = kd.length;
    g.__oai_so_hp = 0;
    g.__oai_so_hw = 0;
    g.__oai_so_s = 0;
    g.__oai_so_k = kd.length;   // Key count
    g.__oai_so_kp = 0;
    g.__oai_so_we = 0;          // wheel number of events
    g.__oai_so_wb = 0;
    g.__oai_so_wl = 0;
    g.__oai_so_fs = 0;
    g.__oai_so_fs2 = 0;
    g.__oai_so_fn = 0;
    g.__oai_so_p = pm;          // pointer event array
    g.__oai_so_pc = pcnt;       // pointer count
    g.__oai_so_i = [];          // input event array
    g.__oai_so_m = pm.length;   // mousemove count
    g.__oai_so_ht = htot;       // Total length of mouse path（hypot Accumulate）
    g.__oai_so_hc = pcnt;       // hypot count
    g.__oai_so_bc = 2;          // click count
    g.__oai_so_bm = 0;
    g.__oai_so_ss = 0;          // scroll Accumulate
    g.__oai_so_ss2 = 0;
    g.__oai_so_sn = 0;          // scroll count
    g.__oai_so_cs = 0;          // click Accumulate
    g.__oai_so_cs2 = 0;
    g.__oai_so_cn = 2;          // click count
    g.__oai_so_st = 0;          // scrollTop
    g.__oai_so_sw = 0;
    g.__oai_so_sp = 0;
    g.__oai_so_spt = 0;
    g.__oai_so_sx0 = 640;
    g.__oai_so_sy0 = 360;
    g.__oai_so_lx = Math.round(px);
    g.__oai_so_ly = Math.round(py);
  })();
})();
