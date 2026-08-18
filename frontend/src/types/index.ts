/* ==========================================================================
   Global type definition
   ========================================================================== */

/** 7 Segment link order */
export const STAGE_ORDER = [
  "checkout", "init", "update", "provider", "approve", "poll", "resolve"
] as const;
export type StageName = typeof STAGE_ORDER[number];

/** oaics custom Checkout 5 Segment link order (pure HTTP, none init/update/approve/poll) */
export const OAICS_STAGE_ORDER = [
  "checkout", "taxes", "provider", "confirm", "resolve"
] as const;
export type OaicsStageName = typeof OAICS_STAGE_ORDER[number];

export const OAICS_STAGE_SHORT: Record<OaicsStageName, string> = {
  checkout: "CK", taxes: "TX",
  provider: "PM", confirm: "CF", resolve: "RS",
};

export const OAICS_STAGE_CN: Record<OaicsStageName, string> = {
  checkout: "Bill, please", taxes: "bill submission",
  provider: "payment provider", confirm: "confirm", resolve: "parse",
};

export const STAGE_SHORT: Record<StageName, string> = {
  checkout: "CK", init: "IN", update: "UP",
  provider: "PM", approve: "AP", poll: "PL", resolve: "RS",
};

export const STAGE_CN: Record<StageName, string> = {
  checkout: "Bill, please", init: "initialization", update: "renew",
  provider: "payment provider", approve: "approve", poll: "polling", resolve: "parse",
};

/** Segment status */
export type StageState = "run" | "ok" | "fail";

export interface StageData {
  state: StageState;
  country: string;
  tryN: number;
  maxTry: number;
  /** real exporting country (Multi-source detection) */
  actualCountry?: string;
  exitIp?: string;
  geoConfidence?: number;
  /** Configuration≠reality => drift */
  drifted?: boolean;
  /** Reuse the same country export in the previous section (same IP No repeated detection) source segment */
  reusedFrom?: string;
}

/** link status */
export type ChainStatus = "running" | "success" | "failed";

/** link mode: cs = Original seventh section (hosted) / oaics = fifth section (custom pure HTTP) */
export type ChainLinkMode = "cs" | "oaics" | "";

/**
 * 【Deprecated】S0 Real-time session type detection segment (2026-08-14 Remove):
 * Originally used to lift the chain at the beginning checkout part IP Additional order detection oaics/cs_live, Now changed to S1 Order creation result
 * Dynamic decision (Whatever you build, go away), Front-end link monitoring list"explore"Column deleted。Types are reserved for compatibility with old data only。
 */
export type ProbeStageName = "probe";

export interface ChainState {
  stages: Partial<Record<StageName | OaicsStageName | ProbeStageName, StageData>>;
  status: ChainStatus;
  email: string;
  tokenSub: string;
  startTime: number;
  attempt: number;
  country: string;
  /** link mode (node: cs/oaics, Marked by backend events) */
  linkMode?: ChainLinkMode;
  /** 【Deprecated】S0 Detected session type (Detection segment has been removed, This field only remains compatible with old data) */
  detected?: string;
  /** real exit (checkout detection) */
  actualCountry?: string;
  exitIp?: string;
  geoConfidence?: number;
  /** Terminal state curing time consumption (Second): No longer continues timing after success */
  elapsed?: number;
  endTime?: number;
  url?: string;
  reason?: string;
  reasonText?: string;
  /** Channel detection results (checkout none promo back init of payment_method_types check) */
  channelDetect?: {
    channel: string;
    methods: string[];
    present: boolean;
    country?: string;
  };
}

/** Token */
export interface Token {
  id: string;
  email: string;
  sub: string;
  account_id: string;
  plan_type: string;
  register_method: string;
  expires_at: string;
  status: string;
  created_at: string;
  last_run_at: string;
  /** Session type detection: cs_live / oaics / error:* / null=Not detected */
  session_type?: string;
  /** Complete detection results: {session_type, token, token_error, promo, paypal, amount} */
  probe?: Record<string, any>;
  /** User tag */
  tags?: string[];
}

/** Agent node */
export interface ProxyNode {
  name: string;
  type: string;
  country_hint: string;
  port: number;
  latency: number;
  healthy: boolean | null;
  concurrent: number;
  max_concurrent: number;
  running: boolean;
}

/** statistics */
export interface Stats {
  success: number;
  failure: number;
  byCountry: Record<string, number>;
  failByCountry: Record<string, number>;
  reasons: Record<string, number>;
  stageMatrix: Record<string, Record<string, { ok: number; fail: number }>>;
}

/** sample record */
export interface Sample {
  ts: string;
  email: string;
  success: boolean;
  reason_code: string;
  reason_text: string;
  paypal_approve_url: string;
  amount_due: number;
  currency: string;
  country: string;
  stage_reached: string;
  chain_id: string;
  /** True export geography (Multi-source detection) */
  actual_country?: string;
  requested_country?: string;
  exit_ip?: string;
  geo_confidence?: number;
}

/** Inventory records */
export interface InventoryRecord {
  ba_id: string;
  email: string;
  country: string;
  paypal_url: string;
  amount: string | number;
  currency: string;
  time: string;
  /** payment channel (Chain branch output) */
  channel?: string;
}

/** log entry */
export interface LogEntry {
  ts: string;
  msg: string;
  level: "ok" | "info" | "warn" | "err";
  chainId: string;
}

/** WebSocket event */
export interface WSEvent {
  type: string;
  [key: string]: any;
}

/* ==========================================================================
   PayPal BA Payment authorization type
   ========================================================================== */

/** BA Authorization process steps */
export const BA_STEPS = [
  "submit_email", "captcha", "sms", "signup", "consent_ba", "done",
] as const;
export type BAStep = typeof BA_STEPS[number];

export const BA_STEP_CN: Record<string, string> = {
  submit_email: "Submit email",
  captcha: "Verification code",
  sms: "SMS verification",
  signup: "Register as a member",
  consent_ba: "Agree to authorize",
  done: "Finish",
  init_session: "Initialize session",
  authorize: "Authorizing",
  failed: "fail",
  FLOW_EXCEPTION: "Process exception",
  AUTHORIZE_EMPTY: "Authorize empty result",
  BUYER_NOT_SET: "No buyer found",
};
export interface BAAuthRecord {
  ba_token: string;
  email: string;
  approve_url: string;
  status: "pending" | "running" | "success" | "failed";
  step: BAStep;
  country: string;
  identity_country?: string;
  proxy_country?: string;
  geo_country?: string;
  chain_id: string;
  /** source: chain=Automatic import of lifting chain / manual=Manual paste / inventory=Restart inventory backfill */
  source?: string;
  captcha_type: "iq" | "pi" | "none" | "";
  sms_phone: string;
  sms_price?: number;
  sms_provider_id?: string;
  last_msg?: string;
  last_level?: string;
  error: string;
  created_at: number;
  updated_at: number;
}

/** Price quotation entry */
export interface SMAQuote {
  provider_id: string;
  price: number;
  count: number;
  currency: string;
  service: string;
}

/** BA Authorization configuration */
export interface BAAuthConfig {
  sms_provider: string;
  sms_api_key?: string; // Code receiving platform API key (Leave short and fall back .env)
  sms_price: string; // Semantics: Upper limit of range (USD/Number), The numbers are taken in ascending order according to the actual price on the platform, starting from the lowest price in the range.
  sms_price_min?: string; // Lower bound of interval (USD/Number), Numbers with prices lower than this will not be taken (default "0" = No limit)
  sms_max_attempts?: number; // Number of number retry rounds (default 12; Cool down after all suppliers fail in each round 2s Try again)
  sms_timeout: number;
  exit_country: string; // Compatibility reserved (Follow the exporting country)
  identity_country?: string; // form country (Follow the queue by default record.country=Chain exporting countries)
  sms_country?: string; // Counter code receiving country (Follow by default identity_country)
  proxy_type: string;
  captcha_strategy: string;
  buyer_mode?: string;
  max_retries: number;
  max_flow_attempts?: number; // Maximum number of process trial rounds (Authorize global retry)
  follow_chain_country?: boolean; // default true: The authorized country follows the chain lifting country
  fail_fast_geo?: boolean; // default true: If the export agent country is inconsistent with the form country, it will fail.
  max_concurrent?: number; // Authorized segment concurrency upper limit
  flow_timeout_s?: number; // Single authorization process times out (Second), default 120
}

/** BA Authorization monitoring log entries (overall situation store, Switch columns/No loss when remounting) */
export interface BAFeedItem {
  ts: number;
  token: string;
  level: "ok" | "info" | "warn" | "err";
  msg: string;
}

/** BA Record polling snapshot (used for feed incremental comparison) */
export interface BABaSnap {
  status: string;
  step: string;
  error: string;
  source: string;
  last_msg: string;
}

/* ==========================================================================
   GPT Account registration
   ========================================================================== */
export interface RegEvent {
  seq: number;
  ts: string;
  type: "start" | "log" | "progress" | "complete" | "error";
  stage?: string;
  message?: string;
  task_id?: string;
  total?: number;
  index?: number;
  ok?: boolean;
  success?: number;
  failed?: number;
  error?: string;
  results?: { index: number; email: string | null; ok: boolean; error: string | null; id: number | null }[];
}

export interface RegAccount {
  id: number;
  email: string;
  alive_status: string;
  plan_type: string;
  source_email: string | null;
  email_mode: string | null;
  status: string;
  error_code: string | null;
  error_detail: string | null;
  register_ts: string | null;
  created_at: string;
  has_password: boolean;
  has_access_token: boolean;
  has_session_token: boolean;
}

export interface RegStatus {
  ok: boolean;
  running: boolean;
  task_id: string | null;
  last_seq: number;
}

/** view name */
export type ViewName =
  | "overview" | "chains" | "logs"
  | "tokens" | "proxy" | "inventory"
  | "momo" | "grok" | "pix" | "paypal" | "paypal_extract"
  | "ideal" | "upi" | "kakao" | "blik" | "twint" | "direct"
  | "bizum" | "gopay" | "naver_pay"
  | "gcash" | "grabpay" | "qris"
  | "direct_pay"
  | "register"
  | "analytics" | "samples" | "settings";

/* ==========================================================================
   lifting chain branch (PayPal refining / MoMo lift chain / Grok link / PIX QR code)
   Each branch is independent: Seven-segment settings / Payment channel verification / token Library / output
   ========================================================================== */
export const BRANCH_NAMES = ["paypal", "momo", "grok", "pix", "ideal", "upi", "kakao", "blik", "twint", "direct",
  "bizum", "gopay", "naver_pay", "gcash", "grabpay", "qris"] as const;
export type BranchName = typeof BRANCH_NAMES[number];

export const BRANCH_CN: Record<BranchName, string> = {
  paypal: "PayPal refining",
  momo: "MoMo lift chain",
  grok: "Grok link",
  pix: "PIX QR code",
  ideal: "iDEAL lift chain",
  upi: "UPI lift chain",
  kakao: "Kakao Pay lift chain",
  blik: "BLIK lift chain",
  twint: "TWINT lift chain",
  direct: "Straight card chain",
  bizum: "Bizum lift chain",
  gopay: "GoPay lift chain",
  naver_pay: "Naver Pay lift chain",
  gcash: "GCash lift chain",
  grabpay: "GrabPay lift chain",
  qris: "QRIS lift chain",
};

export interface StageCfg {
  countries: string[];
  timeout: number;
  retry: number;
  poll_interval?: number;
  max_polls?: number;
}

export interface BranchCfg {
  name: BranchName;
  label: string;
  channel: string;         // Payment channel verification target: paypal / momo / card / link
  token_source: string;    // token library source tag
  require_zero: boolean;   // Amount verification
  channel_check: boolean;  // Payment channel verification
  dual_init: boolean;      // pair init (init0 Borrow the way -> init1 Verify -> init_t transition)
  init0_ccs: string[];     // init0 Take the exit
  init1_ccs: string[];     // init1 Authenticity export
  init_t_ccs: string[];    // Transitional export
  follow_checkout: boolean;// segment follow: remove update All segments outside follow checkout
  billing_country: string; // billing country: "auto"=follow checkout part, Otherwise the country is fixed
  attempts: number; // always try (Every Token Maximum number of rounds to try)
  stages: Partial<Record<StageName, StageCfg>>;
  /** oaics custom Checkout Five paragraph configuration */
  oaics?: OaicsBranchCfg;
}

export interface OaicsBranchCfg {
  label: string;
  billing_country: string; // oaics billing country: "auto"=follow checkout part
  attempts: number;        // oaics Every Checkout Maximum number of rounds to try
  stages: Partial<Record<OaicsStageName, StageCfg>>;
}
