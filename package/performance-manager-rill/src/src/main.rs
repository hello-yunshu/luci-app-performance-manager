// SPDX-License-Identifier: GPL-2.0-only
use std::collections::HashMap;
use std::env;
use std::fs::{self, OpenOptions};
use std::io::{self, Read, Write};
use std::os::fd::AsRawFd;
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const API_VERSION: u64 = 2;
const DEFAULT_SOCKET: &str = "/run/performance-manager/rill.sock";
const DEFAULT_STATE_DIR: &str = "/etc/performance-manager/rill";
const DEFAULT_MAX_MESSAGE: usize = 65_536;
const DEFAULT_TIMEOUT_MS: u64 = 2_000;
const MAX_REQUESTS_PER_SECOND: u32 = 20;
const MIN_RECOMMENDATION_SAMPLES: u64 = 3;
const MAX_OUTCOME_LINES: usize = 2048;
const MAX_LEDGER_LINES: usize = 4096;
const MAX_STATE_FILE_BYTES: u64 = 1_048_576;
const MAX_CONTEXT_KEY_LEN: usize = 512;
const MAX_JSON_DEPTH: usize = 32;
const LEGACY_CONTEXT: &str = "legacy";
const SOL_SOCKET: i32 = 1;
const SO_PEERCRED: i32 = 17;

#[repr(C)]
#[derive(Clone, Copy, Default)]
struct UCred {
    pid: i32,
    uid: u32,
    gid: u32,
}

extern "C" {
    fn getsockopt(
        fd: i32,
        level: i32,
        optname: i32,
        optval: *mut core::ffi::c_void,
        optlen: *mut u32,
    ) -> i32;
}

#[derive(Debug)]
struct Config {
    socket: PathBuf,
    state_dir: PathBuf,
    max_message: usize,
    timeout: Duration,
}

/* ---------------------------------------------------------------------------
 * Strict JSON grammar parser (no external dependencies).
 *
 * The protocol boundary requires a complete, well-formed JSON object: the old
 * token scanners could accept malformed documents that a formal schema would
 * reject.  This parser validates the full grammar (strings, escapes, numbers,
 * arrays, objects, duplicate-key rejection, bounded nesting) so that "the
 * formal schema and the runtime contract" describe the same acceptance set.
 * ------------------------------------------------------------------------- */

#[derive(Debug, Clone, PartialEq)]
enum Json {
    Null,
    Bool(bool),
    Number(f64),
    Str(String),
    Arr(Vec<Json>),
    Obj(Vec<(String, Json)>),
}

impl Json {
    fn get(&self, key: &str) -> Option<&Json> {
        match self {
            Json::Obj(entries) => entries.iter().find(|(k, _)| k == key).map(|(_, v)| v),
            _ => None,
        }
    }

    fn get_str(&self, key: &str) -> Option<&str> {
        match self.get(key) {
            Some(Json::Str(value)) => Some(value),
            _ => None,
        }
    }

    fn get_bool(&self, key: &str) -> Option<bool> {
        match self.get(key) {
            Some(Json::Bool(value)) => Some(*value),
            _ => None,
        }
    }

    fn get_f64(&self, key: &str) -> Option<f64> {
        match self.get(key) {
            Some(Json::Number(value)) if value.is_finite() => Some(*value),
            _ => None,
        }
    }

    fn get_u64(&self, key: &str) -> Option<u64> {
        match self.get(key) {
            Some(Json::Number(value)) if value.is_finite() && value.fract() == 0.0 && *value >= 0.0 && *value <= u64::MAX as f64 => Some(*value as u64),
            _ => None,
        }
    }

    fn get_str_array(&self, key: &str) -> Option<Vec<String>> {
        match self.get(key) {
            Some(Json::Arr(items)) if items.iter().all(|v| matches!(v, Json::Str(_))) => {
                Some(items.iter().filter_map(|v| match v { Json::Str(s) => Some(s.clone()), _ => None }).collect())
            }
            _ => None,
        }
    }
}

struct Parser<'a> {
    input: &'a [u8],
    pos: usize,
    depth: usize,
}

impl<'a> Parser<'a> {
    fn new(input: &'a [u8]) -> Self {
        Self { input, pos: 0, depth: 0 }
    }

    fn skip_ws(&mut self) {
        while self.pos < self.input.len() && matches!(self.input[self.pos], b' ' | b'\t' | b'\r' | b'\n') {
            self.pos += 1;
        }
    }

    fn parse(mut self) -> Result<Json, String> {
        self.skip_ws();
        let value = self.value()?;
        self.skip_ws();
        if self.pos != self.input.len() {
            return Err("trailing-content".to_string());
        }
        Ok(value)
    }

    fn value(&mut self) -> Result<Json, String> {
        self.depth += 1;
        if self.depth > MAX_JSON_DEPTH {
            return Err("nesting-too-deep".to_string());
        }
        let result = self.value_inner();
        self.depth -= 1;
        result
    }

    fn value_inner(&mut self) -> Result<Json, String> {
        self.skip_ws();
        let Some(&b) = self.input.get(self.pos) else {
            return Err("unexpected-end".to_string());
        };
        match b {
            b'{' => self.object(),
            b'[' => self.array(),
            b'"' => Ok(Json::Str(self.string()?)),
            b't' => { self.literal(b"true")?; Ok(Json::Bool(true)) }
            b'f' => { self.literal(b"false")?; Ok(Json::Bool(false)) }
            b'n' => { self.literal(b"null")?; Ok(Json::Null) }
            b'-' | b'0'..=b'9' => self.number(),
            _ => Err("unexpected-token".to_string()),
        }
    }

    fn literal(&mut self, expected: &[u8]) -> Result<(), String> {
        if self.input.get(self.pos..self.pos + expected.len()) == Some(expected) {
            self.pos += expected.len();
            Ok(())
        } else {
            Err("bad-literal".to_string())
        }
    }

    fn object(&mut self) -> Result<Json, String> {
        self.pos += 1;
        let mut entries: Vec<(String, Json)> = Vec::new();
        self.skip_ws();
        if self.input.get(self.pos) == Some(&b'}') {
            self.pos += 1;
            return Ok(Json::Obj(entries));
        }
        loop {
            self.skip_ws();
            let key = self.string()?;
            self.skip_ws();
            if self.input.get(self.pos) != Some(&b':') {
                return Err("missing-colon".to_string());
            }
            self.pos += 1;
            let value = self.value()?;
            if entries.iter().any(|(k, _)| *k == key) {
                return Err(format!("duplicate-key:{key}"));
            }
            entries.push((key, value));
            self.skip_ws();
            match self.input.get(self.pos) {
                Some(b',') => { self.pos += 1; }
                Some(b'}') => { self.pos += 1; return Ok(Json::Obj(entries)); }
                _ => return Err("missing-comma-or-close".to_string()),
            }
        }
    }

    fn array(&mut self) -> Result<Json, String> {
        self.pos += 1;
        let mut items = Vec::new();
        self.skip_ws();
        if self.input.get(self.pos) == Some(&b']') {
            self.pos += 1;
            return Ok(Json::Arr(items));
        }
        loop {
            items.push(self.value()?);
            self.skip_ws();
            match self.input.get(self.pos) {
                Some(b',') => { self.pos += 1; }
                Some(b']') => { self.pos += 1; return Ok(Json::Arr(items)); }
                _ => return Err("missing-comma-or-close".to_string()),
            }
        }
    }

    fn next_hex_digit(&mut self) -> Result<char, String> {
        let Some(&b) = self.input.get(self.pos) else { return Err("unterminated-hex".to_string()); };
        let c = b as char;
        if !c.is_ascii_hexdigit() { return Err("bad-hex-digit".to_string()); }
        self.pos += 1;
        Ok(c)
    }

    fn string(&mut self) -> Result<String, String> {
        if self.input.get(self.pos) != Some(&b'"') {
            return Err("expected-string".to_string());
        }
        self.pos += 1;
        let mut out = String::new();
        loop {
            let Some(&b) = self.input.get(self.pos) else { return Err("unterminated-string".to_string()); };
            match b {
                b'"' => { self.pos += 1; return Ok(out); }
                b'\\' => {
                    self.pos += 1;
                    let Some(&esc) = self.input.get(self.pos) else { return Err("unterminated-escape".to_string()); };
                    self.pos += 1;
                    match esc {
                        b'"' => out.push('"'),
                        b'\\' => out.push('\\'),
                        b'/' => out.push('/'),
                        b'b' => out.push('\u{0008}'),
                        b'f' => out.push('\u{000c}'),
                        b'n' => out.push('\n'),
                        b'r' => out.push('\r'),
                        b't' => out.push('\t'),
                        b'u' => {
                            let mut hex = String::with_capacity(4);
                            for _ in 0..4 { hex.push(self.next_hex_digit()?); }
                            let mut cp = u32::from_str_radix(&hex, 16).map_err(|_| "bad-hex-escape".to_string())?;
                            if (0xD800..=0xDBFF).contains(&cp) {
                                if self.input.get(self.pos..self.pos + 2) != Some(b"\\u") {
                                    return Err("lone-high-surrogate".to_string());
                                }
                                self.pos += 2;
                                let mut low_hex = String::with_capacity(4);
                                for _ in 0..4 { low_hex.push(self.next_hex_digit()?); }
                                let low = u32::from_str_radix(&low_hex, 16).map_err(|_| "bad-hex-escape".to_string())?;
                                if !(0xDC00..=0xDFFF).contains(&low) {
                                    return Err("bad-low-surrogate".to_string());
                                }
                                cp = 0x10000 + ((cp - 0xD800) << 10) + (low - 0xDC00);
                            } else if (0xDC00..=0xDFFF).contains(&cp) {
                                return Err("lone-low-surrogate".to_string());
                            }
                            out.push(char::from_u32(cp).ok_or("bad-codepoint".to_string())?);
                        }
                        _ => return Err("bad-escape".to_string()),
                    }
                }
                0x00..=0x1f => return Err("control-char-in-string".to_string()),
                _ => {
                    let len = utf8_seq_len(b);
                    if len == 0 || self.pos + len > self.input.len() {
                        return Err("bad-utf8".to_string());
                    }
                    let slice = std::str::from_utf8(&self.input[self.pos..self.pos + len]).map_err(|_| "bad-utf8".to_string())?;
                    out.push_str(slice);
                    self.pos += len;
                }
            }
        }
    }

    fn number(&mut self) -> Result<Json, String> {
        let begin = self.pos;
        if self.input.get(self.pos) == Some(&b'-') {
            self.pos += 1;
        }
        match self.input.get(self.pos) {
            Some(b'0') => { self.pos += 1; }
            Some(b'1'..=b'9') => {
                while matches!(self.input.get(self.pos), Some(b'0'..=b'9')) { self.pos += 1; }
            }
            _ => return Err("bad-number".to_string()),
        }
        if self.input.get(self.pos) == Some(&b'.') {
            self.pos += 1;
            let frac_begin = self.pos;
            while matches!(self.input.get(self.pos), Some(b'0'..=b'9')) { self.pos += 1; }
            if self.pos == frac_begin { return Err("bad-fraction".to_string()); }
        }
        if matches!(self.input.get(self.pos), Some(b'e') | Some(b'E')) {
            self.pos += 1;
            if matches!(self.input.get(self.pos), Some(b'+') | Some(b'-')) { self.pos += 1; }
            let exp_begin = self.pos;
            while matches!(self.input.get(self.pos), Some(b'0'..=b'9')) { self.pos += 1; }
            if self.pos == exp_begin { return Err("bad-exponent".to_string()); }
        }
        let text = std::str::from_utf8(&self.input[begin..self.pos]).map_err(|_| "bad-number".to_string())?;
        let value: f64 = text.parse().map_err(|_| "bad-number".to_string())?;
        if !value.is_finite() { return Err("non-finite-number".to_string()); }
        Ok(Json::Number(value))
    }
}

fn utf8_seq_len(leading: u8) -> usize {
    if leading < 0x80 { 1 }
    else if (0xC2..=0xDF).contains(&leading) { 2 }
    else if (0xE0..=0xEF).contains(&leading) { 3 }
    else if (0xF0..=0xF4).contains(&leading) { 4 }
    else { 0 }
}

fn parse_json(text: &str) -> Result<Json, String> {
    Parser::new(text.as_bytes()).parse()
}

fn escape_json(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 8);
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c.is_control() => out.push('?'),
            _ => out.push(c),
        }
    }
    out
}

fn canonical_json(v: &Json, out: &mut String) {
    match v {
        Json::Null => out.push_str("null"),
        Json::Bool(true) => out.push_str("true"),
        Json::Bool(false) => out.push_str("false"),
        Json::Number(n) => out.push_str(&format!("{n}")),
        Json::Str(s) => { out.push('"'); out.push_str(&escape_json(s)); out.push('"'); }
        Json::Arr(items) => {
            out.push('[');
            for (i, item) in items.iter().enumerate() {
                if i > 0 { out.push(','); }
                canonical_json(item, out);
            }
            out.push(']');
        }
        Json::Obj(entries) => {
            out.push('{');
            for (i, (key, value)) in entries.iter().enumerate() {
                if i > 0 { out.push(','); }
                out.push('"'); out.push_str(&escape_json(key)); out.push('"'); out.push(':');
                canonical_json(value, out);
            }
            out.push('}');
        }
    }
}

fn fnv1a64(bytes: &[u8]) -> u64 {
    let mut hash: u64 = 0xcbf2_9ce4_8422_2325;
    for b in bytes {
        hash ^= *b as u64;
        hash = hash.wrapping_mul(0x0000_0100_0000_01b3);
    }
    hash
}

fn digest(v: &Json) -> u64 {
    let mut canonical = String::new();
    canonical_json(v, &mut canonical);
    fnv1a64(canonical.as_bytes())
}

/* ---------------------------------------------------------------------------
 * Model: weighted contextual bandit partitioned by ContextKey.
 *
 * Every outcome is bound to the bounded ContextKey of the experiment that
 * produced it.  A context change (capability, topology, path, route, workload
 * or integration fingerprint) therefore never reuses evidence from an older
 * context: the current partition starts empty and a recommendation cannot
 * reappear until the new context reaches the minimum evidence threshold.
 * ------------------------------------------------------------------------- */

#[derive(Debug, Clone, Default)]
struct ActionStats {
    samples: u64,
    controlled_ab: u64,
    passive: u64,
    health_only: u64,
    weighted_reward: f64,
    total_weight: f64,
    last_reward: f64,
}

impl ActionStats {
    fn update(&mut self, measurement: &str, reward: f64) {
        let weight = match measurement {
            "controlled_ab" => { self.controlled_ab += 1; 1.0 }
            "passive_before_after" => { self.passive += 1; 0.5 }
            "health_only" => { self.health_only += 1; 0.1 }
            _ => return,
        };
        self.samples += 1;
        self.weighted_reward += reward * weight;
        self.total_weight += weight;
        self.last_reward = reward;
    }

    fn mean_reward(&self) -> f64 {
        if self.total_weight > 0.0 { self.weighted_reward / self.total_weight } else { 0.0 }
    }
}

#[derive(Debug, Clone, Default)]
struct ObserveMeta {
    device_profile: Option<String>,
    workload_class: Vec<String>,
    path_id: Option<String>,
    route_identity: Option<String>,
    integration_fingerprint: Option<String>,
    integrations_digest: Option<u64>,
    metrics_digest: Option<u64>,
}

#[derive(Debug, Clone, Default)]
struct AvailableAction {
    id: String,
    apply_scope: Option<String>,
    apply_target: Option<String>,
    evaluation_paths: Vec<String>,
    risk: Option<String>,
}

#[derive(Debug)]
struct RuntimeState {
    started: Instant,
    observations: u64,
    outcomes: u64,
    accepted: u64,
    rejected: u64,
    drift_events: u64,
    persistent_writes: u64,
    rate_window: Instant,
    rate_count: u32,
    current_context: Option<String>,
    last_observe_meta: Option<ObserveMeta>,
    last_drift_epoch: Option<u64>,
    last_available_actions: Vec<AvailableAction>,
    context_partitions: HashMap<String, HashMap<String, ActionStats>>,
}

fn context_components(key: &str) -> HashMap<String, String> {
    let mut out = HashMap::new();
    for part in key.split(';') {
        if let Some((name, value)) = part.split_once('=') {
            out.insert(name.to_string(), value.to_string());
        }
    }
    out
}

fn context_diff_reasons(prev: &str, now: &str) -> String {
    let before = context_components(prev);
    let after = context_components(now);
    let mut reasons: Vec<String> = Vec::new();
    for component in ["profile", "cap", "topo", "path", "route", "workload", "integ"] {
        if before.get(component) != after.get(component) {
            reasons.push(component.to_string());
        }
    }
    if reasons.is_empty() { "context-key".to_string() } else { reasons.join(",") }
}

impl RuntimeState {
    fn new(state_dir: &Path) -> Self {
        let mut state = Self {
            started: Instant::now(),
            observations: 0,
            outcomes: 0,
            accepted: 0,
            rejected: 0,
            drift_events: 0,
            persistent_writes: 0,
            rate_window: Instant::now(),
            rate_count: 0,
            current_context: None,
            last_observe_meta: None,
            last_drift_epoch: None,
            last_available_actions: Vec::new(),
            context_partitions: HashMap::new(),
        };
        state.load_outcomes(state_dir);
        state
    }

    fn load_outcomes(&mut self, state_dir: &Path) {
        let path = state_dir.join("validated-outcomes.tsv");
        let _ = compact_text_file(&path, MAX_OUTCOME_LINES, MAX_STATE_FILE_BYTES);
        let Ok(text) = fs::read_to_string(path) else { return; };
        let lines: Vec<&str> = text.lines().collect();
        let start = lines.len().saturating_sub(MAX_OUTCOME_LINES);
        for line in &lines[start..] {
            let cols: Vec<&str> = line.split('\t').collect();
            /* Current format: epoch, context, action, measurement, reward,
             * session.  Legacy 5-column rows predate context binding and are
             * kept only in an inert "legacy" partition that never matches a
             * live ContextKey: stale-context evidence must not be reused. */
            let (context, action, measurement, reward) = if cols.len() >= 6 {
                (cols[1].to_string(), cols[2], cols[3], cols[4])
            } else if cols.len() == 5 {
                (LEGACY_CONTEXT.to_string(), cols[1], cols[2], cols[3])
            } else {
                continue;
            };
            if context.len() > MAX_CONTEXT_KEY_LEN { continue; }
            let Ok(reward) = reward.parse::<f64>() else { continue; };
            if !reward.is_finite() { continue; }
            self.context_partitions.entry(context).or_default().entry(action.to_string()).or_default().update(measurement, reward);
            self.outcomes += 1;
        }
    }

    fn permit(&mut self) -> bool {
        if self.rate_window.elapsed() >= Duration::from_secs(1) {
            self.rate_window = Instant::now();
            self.rate_count = 0;
        }
        if self.rate_count >= MAX_REQUESTS_PER_SECOND {
            self.rejected += 1;
            return false;
        }
        self.rate_count += 1;
        true
    }

    fn observe_context(&mut self, request: &Json, state_dir: &Path) -> Result<(), String> {
        let context_key = request.get_str("contextKey").ok_or("missing-context-key")?;
        if context_key.len() > MAX_CONTEXT_KEY_LEN {
            return Err("context-key-too-long".to_string());
        }
        self.last_observe_meta = Some(ObserveMeta {
            device_profile: request.get_str("deviceProfile").map(str::to_string),
            workload_class: request.get_str_array("workloadClass").unwrap_or_default(),
            path_id: request.get_str("pathId").map(str::to_string),
            route_identity: request.get_str("routeIdentity").map(str::to_string),
            integration_fingerprint: request.get_str("integrationFingerprint").map(str::to_string),
            integrations_digest: request.get("integrations").map(digest),
            metrics_digest: request.get("context").map(digest),
        });
        let actions = parse_available_actions(request)?;
        if !actions.is_empty() {
            self.last_available_actions = actions;
        }
        if let Some(prev) = &self.current_context {
            if prev != context_key {
                self.drift_events += 1;
                self.last_drift_epoch = Some(epoch_seconds());
                let reasons = context_diff_reasons(prev, context_key);
                if append_ledger(state_dir, "context_drift", None, None, Some(&reasons)).is_ok() {
                    self.persistent_writes += 1;
                }
            }
        }
        self.current_context = Some(context_key.to_string());
        Ok(())
    }

    fn update_outcome(&mut self, context: &str, action: &str, measurement: &str, reward: f64) {
        self.context_partitions.entry(context.to_string()).or_default().entry(action.to_string()).or_default().update(measurement, reward);
        self.outcomes += 1;
    }

    fn recommendation_json(&self) -> String {
        let Some(context) = &self.current_context else { return "[]".to_string(); };
        let Some(partition) = self.context_partitions.get(context) else { return "[]".to_string(); };
        let mut best: Option<(&str, &ActionStats, f64)> = None;
        for action in &self.last_available_actions {
            let Some(stats) = partition.get(&action.id) else { continue; };
            if stats.samples < MIN_RECOMMENDATION_SAMPLES { continue; }
            let mean = stats.mean_reward();
            if mean <= 0.0 || !mean.is_finite() { continue; }
            match best {
                Some((_, _, current)) if current >= mean => {}
                _ => best = Some((action.id.as_str(), stats, mean)),
            }
        }
        let Some((action, stats, mean)) = best else { return "[]".to_string(); };
        let confidence = if stats.controlled_ab >= 3 { "high" } else if stats.samples >= 6 { "medium" } else { "low" };
        format!(
            "[{{\"actionId\":\"{}\",\"disposition\":\"advisory\",\"confidence\":\"{}\",\"meanReward\":{:.6},\"validatedSamples\":{},\"controlledAbSamples\":{},\"authority\":\"none\"}}]",
            escape_json(action), confidence, mean, stats.samples, stats.controlled_ab
        )
    }

    fn model_health_json(&self) -> String {
        let current = self.current_context.clone().unwrap_or_default();
        let current_ready = self.context_partitions.get(&current)
            .map(|partition| partition.values().filter(|s| s.samples >= MIN_RECOMMENDATION_SAMPLES).count())
            .unwrap_or(0);
        format!(
            "{{\"algorithm\":\"weighted-contextual-bandit-shadow\",\"contextPartitions\":{},\"currentContext\":{},\"currentContextReadyActions\":{},\"driftEvents\":{},\"lastDriftEpoch\":{},\"minimumSamples\":{}}}",
            self.context_partitions.len(),
            if current.is_empty() { "null".to_string() } else { format!("\"{}\"", escape_json(&current)) },
            current_ready,
            self.drift_events,
            self.last_drift_epoch.map(|v| v.to_string()).unwrap_or_else(|| "null".to_string()),
            MIN_RECOMMENDATION_SAMPLES
        )
    }

    fn last_context_json(&self) -> String {
        match &self.current_context {
            Some(context) => format!("\"{}\"", escape_json(context)),
            None => "null".to_string(),
        }
    }

    fn observe_meta_json(&self) -> String {
        let Some(meta) = &self.last_observe_meta else { return "null".to_string(); };
        let workload = format!("[{}]", meta.workload_class.iter().map(|v| format!("\"{}\"", escape_json(v))).collect::<Vec<_>>().join(","));
        let actions = format!("[{}]", self.last_available_actions.iter().map(|a| {
            format!(
                "{{\"id\":\"{}\",\"applyScope\":{},\"applyTarget\":{},\"evaluationPaths\":{},\"risk\":{}}}",
                escape_json(&a.id),
                a.apply_scope.as_deref().map(|v| format!("\"{}\"", escape_json(v))).unwrap_or_else(|| "null".to_string()),
                a.apply_target.as_deref().map(|v| format!("\"{}\"", escape_json(v))).unwrap_or_else(|| "null".to_string()),
                format!("[{}]", a.evaluation_paths.iter().map(|v| format!("\"{}\"", escape_json(v))).collect::<Vec<_>>().join(",")),
                a.risk.as_deref().map(|v| format!("\"{}\"", escape_json(v))).unwrap_or_else(|| "null".to_string()),
            )
        }).collect::<Vec<_>>().join(","));
        format!(
            "{{\"deviceProfile\":{},\"workloadClass\":{},\"pathId\":{},\"routeIdentity\":{},\"integrationFingerprint\":{},\"integrationsDigest\":{},\"metricsDigest\":{},\"availableActions\":{}}}",
            meta.device_profile.as_deref().map(|v| format!("\"{}\"", escape_json(v))).unwrap_or_else(|| "null".to_string()),
            workload,
            meta.path_id.as_deref().map(|v| format!("\"{}\"", escape_json(v))).unwrap_or_else(|| "null".to_string()),
            meta.route_identity.as_deref().map(|v| format!("\"{}\"", escape_json(v))).unwrap_or_else(|| "null".to_string()),
            meta.integration_fingerprint.as_deref().map(|v| format!("\"{}\"", escape_json(v))).unwrap_or_else(|| "null".to_string()),
            meta.integrations_digest.map(|v| v.to_string()).unwrap_or_else(|| "null".to_string()),
            meta.metrics_digest.map(|v| v.to_string()).unwrap_or_else(|| "null".to_string()),
            actions
        )
    }
}

fn parse_available_actions(request: &Json) -> Result<Vec<AvailableAction>, String> {
    let Some(Json::Arr(items)) = request.get("availableActions") else {
        return Err("invalid-field:availableActions".to_string());
    };
    let mut out = Vec::new();
    for item in items {
        let Some(id) = item.get_str("id") else { return Err("invalid-field:availableActions".to_string()); };
        if id.is_empty() { return Err("invalid-field:availableActions".to_string()); }
        out.push(AvailableAction {
            id: id.to_string(),
            apply_scope: item.get_str("applyScope").map(str::to_string),
            apply_target: item.get_str("applyTarget").map(str::to_string),
            evaluation_paths: item.get_str_array("evaluationPaths").unwrap_or_default(),
            risk: item.get_str("risk").map(str::to_string),
        });
    }
    Ok(out)
}

/* ---------------------------------------------------------------------------
 * Per-op validation.  These acceptance rules mirror the formal
 * contracts/rill-ipc.schema.json (the Python contract tests assert that the
 * schema's required sets and this code describe the same acceptance set).
 * ------------------------------------------------------------------------- */

fn validate_envelope(v: &Json) -> Result<(String, String), String> {
    if !matches!(v, Json::Obj(_)) {
        return Err("bad-protocol-envelope".to_string());
    }
    if v.get_u64("api") != Some(API_VERSION) {
        return Err("unsupported-api".to_string());
    }
    let request_id = v.get_str("requestId").ok_or("missing-request-id")?;
    let op = v.get_str("op").ok_or("missing-op")?;
    Ok((request_id.to_string(), op.to_string()))
}

fn require_str(v: &Json, key: &str) -> Result<(), String> {
    let value = v.get_str(key).ok_or_else(|| format!("missing-field:{key}"))?;
    if value.is_empty() {
        return Err(format!("empty-field:{key}"));
    }
    Ok(())
}

fn require_context_key(v: &Json) -> Result<(), String> {
    let key = v.get_str("contextKey").ok_or("missing-context-key")?;
    if !key.starts_with("ctx-v1:") {
        return Err("invalid-context-key-prefix".to_string());
    }
    if key.len() > MAX_CONTEXT_KEY_LEN {
        return Err("context-key-too-long".to_string());
    }
    Ok(())
}

fn validate_observe(v: &Json) -> Result<(), String> {
    for key in ["deviceProfile", "capabilityHash", "pathId", "routeIdentity", "integrationFingerprint"] {
        require_str(v, key)?;
    }
    require_context_key(v)?;
    if v.get_u64("topologyGeneration").is_none() {
        return Err("invalid-field:topologyGeneration".to_string());
    }
    if !matches!(v.get_str("measurementClass"), Some("controlled_ab" | "passive_before_after" | "health_only")) {
        return Err("invalid-field:measurementClass".to_string());
    }
    if !matches!(v.get("context"), Some(Json::Obj(_))) {
        return Err("invalid-field:context".to_string());
    }
    if !matches!(v.get("integrations"), Some(Json::Obj(_))) {
        return Err("invalid-field:integrations".to_string());
    }
    if !matches!(v.get("workloadClass"), Some(Json::Arr(items)) if !items.is_empty() && items.iter().all(|x| matches!(x, Json::Str(_)))) {
        return Err("invalid-field:workloadClass".to_string());
    }
    parse_available_actions(v).map(|_| ())
}

fn validate_outcome(v: &Json) -> Result<(String, String, f64, String, String), String> {
    if v.get_bool("validated") != Some(true) {
        return Err("outcome-not-validated".to_string());
    }
    require_context_key(v)?;
    for key in ["actionId", "sessionId", "deviceProfile", "capabilityHash", "pathId", "routeIdentity", "integrationFingerprint"] {
        require_str(v, key)?;
    }
    if v.get_u64("topologyGeneration").is_none() {
        return Err("invalid-field:topologyGeneration".to_string());
    }
    if !matches!(v.get("workloadClass"), Some(Json::Arr(items)) if !items.is_empty()) {
        return Err("invalid-field:workloadClass".to_string());
    }
    let measurement = v.get_str("measurementClass").ok_or("missing-measurement-class")?.to_string();
    if !matches!(measurement.as_str(), "controlled_ab" | "passive_before_after" | "health_only") {
        return Err("invalid-measurement-class".to_string());
    }
    let reward = v.get_f64("reward").ok_or("invalid-reward")?;
    Ok((
        v.get_str("actionId").unwrap().to_string(),
        measurement,
        reward,
        v.get_str("sessionId").unwrap().to_string(),
        v.get_str("contextKey").unwrap().to_string(),
    ))
}

fn parse_args() -> Config {
    let mut socket = PathBuf::from(DEFAULT_SOCKET);
    let mut state_dir = PathBuf::from(DEFAULT_STATE_DIR);
    let mut max_message = DEFAULT_MAX_MESSAGE;
    let mut timeout_ms = DEFAULT_TIMEOUT_MS;
    let mut args = env::args().skip(1);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--socket" => if let Some(v) = args.next() { socket = PathBuf::from(v); },
            "--state-dir" => if let Some(v) = args.next() { state_dir = PathBuf::from(v); },
            "--max-message" => if let Some(v) = args.next() {
                if let Ok(n) = v.parse::<usize>() { max_message = n.clamp(1024, 262_144); }
            },
            "--timeout-ms" => if let Some(v) = args.next() {
                if let Ok(n) = v.parse::<u64>() { timeout_ms = n.clamp(250, 10_000); }
            },
            "--help" | "-h" => {
                println!("performance-manager-rill [--socket PATH] [--state-dir PATH] [--max-message BYTES] [--timeout-ms MS]");
                std::process::exit(0);
            }
            _ => {}
        }
    }
    Config { socket, state_dir, max_message, timeout: Duration::from_millis(timeout_ms) }
}

fn peer_cred(stream: &UnixStream) -> io::Result<UCred> {
    let mut cred = UCred::default();
    let mut len = std::mem::size_of::<UCred>() as u32;
    let rc = unsafe {
        getsockopt(
            stream.as_raw_fd(), SOL_SOCKET, SO_PEERCRED,
            &mut cred as *mut UCred as *mut core::ffi::c_void,
            &mut len as *mut u32,
        )
    };
    if rc != 0 || len as usize != std::mem::size_of::<UCred>() { return Err(io::Error::last_os_error()); }
    Ok(cred)
}

fn read_limited(stream: &mut UnixStream, max: usize) -> io::Result<Vec<u8>> {
    let mut out = Vec::with_capacity(max.min(4096));
    let mut buf = [0u8; 4096];
    loop {
        let n = stream.read(&mut buf)?;
        if n == 0 { break; }
        for b in &buf[..n] {
            if *b == b'\n' { return Ok(out); }
            if out.len() >= max { return Err(io::Error::new(io::ErrorKind::InvalidData, "message-too-large")); }
            out.push(*b);
        }
    }
    Ok(out)
}

fn epoch_seconds() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs()
}

fn compact_text_file(path: &Path, max_lines: usize, max_bytes: u64) -> io::Result<()> {
    let Ok(meta) = fs::metadata(path) else { return Ok(()); };
    if meta.len() <= max_bytes {
        let text = fs::read_to_string(path)?;
        if text.lines().count() <= max_lines { return Ok(()); }
    }
    let text = fs::read_to_string(path)?;
    let lines: Vec<&str> = text.lines().collect();
    let start = lines.len().saturating_sub(max_lines);
    let mut out = lines[start..].join("\n");
    if !out.is_empty() { out.push('\n'); }
    let tmp = path.with_extension("compact.tmp");
    fs::write(&tmp, out.as_bytes())?;
    fs::rename(tmp, path)?;
    Ok(())
}

fn bounded_append(path: &Path, line: &str, max_lines: usize) -> io::Result<()> {
    compact_text_file(path, max_lines, MAX_STATE_FILE_BYTES)?;
    let mut f = OpenOptions::new().create(true).append(true).open(path)?;
    f.write_all(line.as_bytes())?;
    f.flush()?;
    if fs::metadata(path).map(|m| m.len()).unwrap_or(0) > MAX_STATE_FILE_BYTES {
        compact_text_file(path, max_lines, MAX_STATE_FILE_BYTES)?;
    }
    Ok(())
}

fn sanitize_tsv(s: &str) -> String {
    s.chars().map(|c| if matches!(c, '\t' | '\n' | '\r') { '_' } else { c }).collect()
}

fn append_validated_outcome(state_dir: &Path, context: &str, action: &str, measurement: &str, reward: f64, session: &str) -> io::Result<()> {
    let line = format!(
        "{}\t{}\t{}\t{}\t{}\t{}\n",
        epoch_seconds(), sanitize_tsv(context), sanitize_tsv(action), measurement, reward, sanitize_tsv(session)
    );
    bounded_append(&state_dir.join("validated-outcomes.tsv"), &line, MAX_OUTCOME_LINES)
}

fn append_ledger(state_dir: &Path, event: &str, action: Option<&str>, reward: Option<f64>, detail: Option<&str>) -> io::Result<()> {
    let line = format!(
        "{{\"epoch\":{},\"event\":\"{}\",\"actionId\":{},\"reward\":{},\"detail\":{}}}\n",
        epoch_seconds(), escape_json(event),
        action.map(|v| format!("\"{}\"", escape_json(v))).unwrap_or_else(|| "null".to_string()),
        reward.map(|v| format!("{:.6}", v)).unwrap_or_else(|| "null".to_string()),
        detail.map(|v| format!("\"{}\"", escape_json(v))).unwrap_or_else(|| "null".to_string()),
    );
    bounded_append(&state_dir.join("decision-ledger.jsonl"), &line, MAX_LEDGER_LINES)
}

fn response(request_id: &str, body: &str) -> String {
    format!("{{\"api\":{},\"requestId\":\"{}\",{} }}\n", API_VERSION, escape_json(request_id), body)
}

fn error_response(request_id: &str, code: &str) -> String {
    response(request_id, &format!("\"ok\":false,\"error\":\"{}\"", escape_json(code)))
}

fn handle_request(request: &str, runtime: &mut RuntimeState, cfg: &Config) -> String {
    let parsed = match parse_json(request) {
        Ok(value) => value,
        Err(e) => return error_response("unknown", &format!("bad-json:{e}")),
    };
    let (request_id, op) = match validate_envelope(&parsed) {
        Ok(identity) => identity,
        Err(e) => return error_response("unknown", &e),
    };
    match op.as_str() {
        "status" => response(&request_id, &format!(
            "\"ok\":true,\"mode\":\"shadow\",\"state\":\"learning\",\"observations\":{},\"validatedOutcomes\":{},\"accepted\":{},\"rejected\":{},\"uptimeSeconds\":{},\"driftEvents\":{},\"persistentWrites\":{},\"lastContext\":{},\"lastObserve\":{},\"modelHealth\":{},\"recommendations\":{}",
            runtime.observations, runtime.outcomes, runtime.accepted, runtime.rejected,
            runtime.started.elapsed().as_secs(), runtime.drift_events, runtime.persistent_writes,
            runtime.last_context_json(), runtime.observe_meta_json(),
            runtime.model_health_json(), runtime.recommendation_json()
        )),
        "observe" => {
            if let Err(e) = validate_observe(&parsed) {
                return error_response(&request_id, &e);
            }
            runtime.observations += 1;
            if let Err(e) = runtime.observe_context(&parsed, &cfg.state_dir) {
                return error_response(&request_id, &e);
            }
            response(&request_id, &format!(
                "\"ok\":true,\"mode\":\"shadow\",\"state\":\"learning\",\"accepted\":true,\"modelHealth\":{},\"recommendations\":{}",
                runtime.model_health_json(), runtime.recommendation_json()
            ))
        }
        "outcome" => {
            let (action, measurement, reward, session, context) = match validate_outcome(&parsed) {
                Ok(fields) => fields,
                Err(e) => return error_response(&request_id, &e),
            };
            match append_validated_outcome(&cfg.state_dir, &context, &action, &measurement, reward, &session) {
                Ok(()) => {
                    runtime.persistent_writes += 1;
                    runtime.update_outcome(&context, &action, &measurement, reward);
                    let detail = format!("measurement={measurement};session={session}");
                    if append_ledger(&cfg.state_dir, "validated_outcome", Some(&action), Some(reward), Some(&detail)).is_ok() {
                        runtime.persistent_writes += 1;
                    }
                    response(&request_id, &format!(
                        "\"ok\":true,\"mode\":\"shadow\",\"state\":\"learning\",\"stored\":true,\"modelHealth\":{},\"recommendations\":{}",
                        runtime.model_health_json(), runtime.recommendation_json()
                    ))
                }
                Err(e) => error_response(&request_id, &format!("outcome-rejected:{e}")),
            }
        }
        _ => error_response(&request_id, "unsupported-op"),
    }
}

fn handle_connection(mut stream: UnixStream, runtime: &mut RuntimeState, cfg: &Config) -> io::Result<()> {
    stream.set_read_timeout(Some(cfg.timeout))?;
    stream.set_write_timeout(Some(cfg.timeout))?;
    let cred = peer_cred(&stream)?;
    if cred.uid != 0 {
        runtime.rejected += 1;
        let _ = stream.write_all(error_response("unknown", "peer-not-authorized").as_bytes());
        return Ok(());
    }
    if !runtime.permit() {
        let _ = stream.write_all(error_response("unknown", "rate-limited").as_bytes());
        return Ok(());
    }
    let raw = match read_limited(&mut stream, cfg.max_message) {
        Ok(v) => v,
        Err(e) => {
            runtime.rejected += 1;
            let _ = stream.write_all(error_response("unknown", &e.to_string()).as_bytes());
            return Ok(());
        }
    };
    let request = match std::str::from_utf8(&raw) {
        Ok(s) => s,
        Err(_) => {
            runtime.rejected += 1;
            let _ = stream.write_all(error_response("unknown", "invalid-utf8").as_bytes());
            return Ok(());
        }
    };
    runtime.accepted += 1;
    let reply = handle_request(request, runtime, cfg);
    stream.write_all(reply.as_bytes())?;
    Ok(())
}

fn main() -> io::Result<()> {
    let cfg = parse_args();
    fs::create_dir_all(&cfg.state_dir)?;
    if let Some(parent) = cfg.socket.parent() { fs::create_dir_all(parent)?; }
    if cfg.socket.exists() { fs::remove_file(&cfg.socket)?; }
    let listener = UnixListener::bind(&cfg.socket)?;
    fs::set_permissions(&cfg.socket, fs::Permissions::from_mode(0o660))?;
    eprintln!("performance-manager-rill: Shadow learning on {}", cfg.socket.display());
    let mut runtime = RuntimeState::new(&cfg.state_dir);
    for conn in listener.incoming() {
        match conn {
            Ok(stream) => {
                if let Err(e) = handle_connection(stream, &mut runtime, &cfg) {
                    runtime.rejected += 1;
                    eprintln!("performance-manager-rill: request error: {e}");
                }
            }
            Err(e) => eprintln!("performance-manager-rill: accept error: {e}"),
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[cfg(target_os = "linux")]
    use std::os::unix::fs::MetadataExt;

    fn temp_state(name: &str) -> PathBuf {
        let p = env::temp_dir().join(format!("pm-rill-test-{}-{}", name, std::process::id()));
        let _ = fs::remove_dir_all(&p);
        fs::create_dir_all(&p).unwrap();
        p
    }

    fn test_config(dir: &Path) -> Config {
        Config { socket: dir.join("sock"), state_dir: dir.to_path_buf(), max_message: 65536, timeout: Duration::from_secs(1) }
    }

    fn context_key(cap: &str) -> String {
        format!("ctx-v1:profile=recommended;cap={};topo=9;path=path:lan-to-wan;route=abc123;workload=w1;integ=deadbeef", cap)
    }

    fn outcome_payload(cap: &str, action: &str, reward: f64, validated: bool) -> String {
        format!(
            r#"{{"api":2,"requestId":"x","op":"outcome","validated":{},"actionId":"{}","measurementClass":"controlled_ab","reward":{},"sessionId":"s1","deviceProfile":"recommended","capabilityHash":"{}","topologyGeneration":9,"pathId":"path:lan-to-wan","routeIdentity":"r1","workloadClass":["plain_forwarding"],"integrationFingerprint":"f1","contextKey":"{}"}}"#,
            validated, action, reward, cap, context_key(cap)
        )
    }

    fn outcome_payload_missing(cap: &str, skip: &str) -> String {
        let fields = [
            r#""validated":true"#,
            r#""actionId":"nic.ring.floor""#,
            r#""measurementClass":"controlled_ab""#,
            r#""reward":0.5"#,
            r#""sessionId":"s1""#,
            r#""deviceProfile":"recommended""#,
            &format!(r#""capabilityHash":"{}""#, cap),
            r#""topologyGeneration":9"#,
            r#""pathId":"path:lan-to-wan""#,
            r#""routeIdentity":"r1""#,
            r#""workloadClass":["plain_forwarding"]"#,
            r#""integrationFingerprint":"f1""#,
            &format!(r#""contextKey":"{}""#, context_key(cap)),
        ];
        let skip_prefix = format!(r#""{}":"#, skip);
        let kept: Vec<&str> = fields.iter().filter(|f| !f.starts_with(&skip_prefix)).map(|f| *f).collect();
        format!(r#"{{"api":2,"requestId":"x","op":"outcome",{}}}"#, kept.join(","))
    }

    fn observe_payload(cap: &str, actions: &str) -> String {
        format!(
            r#"{{"api":2,"requestId":"o","op":"observe","deviceProfile":"recommended","capabilityHash":"{}","topologyGeneration":9,"pathId":"path:lan-to-wan","routeIdentity":"r1","workloadClass":["plain_forwarding"],"measurementClass":"passive_before_after","context":{{"cpuCount":4}},"integrations":{{"sqm":false}},"integrationFingerprint":"f1","contextKey":"{}","availableActions":{}}}"#,
            cap, context_key(cap), actions
        )
    }

    #[test]
    fn read_limited_preserves_first_chunk_and_bounds_input() {
        let (mut writer, mut reader) = UnixStream::pair().unwrap();
        writer.write_all(b"{\"api\":2}\nignored").unwrap();
        assert_eq!(read_limited(&mut reader, 128).unwrap(), b"{\"api\":2}".to_vec());

        let (mut writer2, mut reader2) = UnixStream::pair().unwrap();
        writer2.write_all(b"abcdef\n").unwrap();
        let err = read_limited(&mut reader2, 5).unwrap_err();
        assert_eq!(err.kind(), io::ErrorKind::InvalidData);
    }

    #[test]
    fn read_timeout_bounds_peer_wait() {
        let (server, mut client) = UnixStream::pair().unwrap();
        client.set_read_timeout(Some(Duration::from_millis(120))).unwrap();
        let started = Instant::now();
        let err = read_limited(&mut client, 65536).unwrap_err();
        assert!(matches!(err.kind(), io::ErrorKind::WouldBlock | io::ErrorKind::TimedOut));
        assert!(started.elapsed() >= Duration::from_millis(100));
        let _ = server;
    }

    #[test]
    fn strict_parser_rejects_bad_grammar() {
        assert!(parse_json(r#"{"api":2,"requestId":"x","op":"status"}"#).is_ok());
        assert!(parse_json(r#"junk {"api":2}"#).is_err());
        assert!(parse_json(r#"{"api":2,"api":2}"#).is_err());
        assert!(parse_json(r#"{"api":2 "requestId":"x"}"#).is_err());
        assert!(parse_json(r#"{"a":01}"#).is_err());
        assert!(parse_json(r#"{"a":1.}"#).is_err());
        assert!(parse_json(r#"{"a":1e}"#).is_err());
        assert!(parse_json(r#"{"a":"\x"}"#).is_err());
        assert!(parse_json(r#"{"a":"\uD800"}"#).is_err());
        assert!(parse_json(r#"{"a":1} trailing"#).is_err());
        assert!(parse_json(r#"{"a":tru}"#).is_err());
        assert!(parse_json(r#"{"a":[1,}"#).is_err());
    }

    #[test]
    fn parser_reads_core_fields() {
        let v = parse_json(r#"{"api":2,"requestId":"x","op":"outcome","validated":true,"reward":0.25,"availableActions":[{"id":"nic.ring.floor","applyScope":"device","evaluationPaths":["path:lan-to-wan"],"risk":"safe"}]}"#).unwrap();
        assert_eq!(v.get_u64("api"), Some(2));
        assert_eq!(v.get_str("op"), Some("outcome"));
        assert_eq!(v.get_bool("validated"), Some(true));
        assert_eq!(v.get_f64("reward"), Some(0.25));
        let actions = parse_available_actions(&v).unwrap();
        assert_eq!(actions.len(), 1);
        assert_eq!(actions[0].id, "nic.ring.floor");
        assert_eq!(actions[0].apply_scope.as_deref(), Some("device"));
        assert_eq!(actions[0].evaluation_paths, vec!["path:lan-to-wan".to_string()]);
    }

    #[test]
    fn parser_decodes_utf8_and_json_escapes() {
        let v = parse_json(r#"{"value":"中文\u0020x\/y\b\f"}"#).unwrap();
        assert_eq!(v.get_str("value"), Some("中文 x/y\u{0008}\u{000c}"));
    }

    #[test]
    fn bad_schema_requests_are_rejected() {
        let dir = temp_state("bad-schema");
        let cfg = test_config(&dir);
        let mut state = RuntimeState::new(&dir);
        let reply = handle_request(r#"{"api":2,"requestId":"x","op":"observe"}"#, &mut state, &cfg);
        assert!(reply.contains("missing-field:deviceProfile"));
        let reply = handle_request(r#"{"api":2,"requestId":"x","op":"outcome","validated":true,"actionId":"a","measurementClass":"controlled_ab","reward":1,"sessionId":"s"}"#, &mut state, &cfg);
        assert!(reply.contains("missing-context-key"));
        assert_eq!(state.outcomes, 0);
        let reply = handle_request(r#"not json"#, &mut state, &cfg);
        assert!(reply.contains("bad-json"));
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn unvalidated_outcome_is_rejected() {
        let dir = temp_state("unvalidated");
        let cfg = test_config(&dir);
        let mut state = RuntimeState::new(&dir);
        let reply = handle_request(&outcome_payload("h1", "nic.ring.floor", 1.0, false), &mut state, &cfg);
        assert!(reply.contains("outcome-not-validated"));
        assert_eq!(state.outcomes, 0);
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn outcome_missing_metadata_is_rejected() {
        let dir = temp_state("outcome-missing-meta");
        let cfg = test_config(&dir);
        let mut state = RuntimeState::new(&dir);
        for field in ["integrationFingerprint", "deviceProfile", "capabilityHash", "pathId", "routeIdentity", "workloadClass", "reward", "sessionId", "contextKey"] {
            let reply = handle_request(&outcome_payload_missing("h1", field), &mut state, &cfg);
            assert!(
                reply.contains("missing-field") || reply.contains("invalid-field") || reply.contains("missing-") || reply.contains("invalid-"),
                "{}: {}", field, reply
            );
            assert_eq!(state.outcomes, 0, "{} must not be recorded", field);
        }
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn validated_outcome_binds_to_context_partition() {
        let dir = temp_state("validated");
        let cfg = test_config(&dir);
        let mut state = RuntimeState::new(&dir);
        let reply = handle_request(&outcome_payload("h1", "nic.ring.floor", 0.5, true), &mut state, &cfg);
        assert!(reply.contains("\"stored\":true"));
        assert_eq!(state.outcomes, 1);
        assert_eq!(state.persistent_writes, 2);
        assert!(state.context_partitions.contains_key(&context_key("h1")));
        let tsv = fs::read_to_string(dir.join("validated-outcomes.tsv")).unwrap();
        assert!(tsv.contains(&context_key("h1")));
        assert!(dir.join("decision-ledger.jsonl").exists());
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn state_files_are_bounded() {
        let dir = temp_state("bounded");
        for i in 0..(MAX_OUTCOME_LINES + 50) {
            append_validated_outcome(&dir, &context_key("h"), "a", "controlled_ab", i as f64, "s").unwrap();
        }
        compact_text_file(&dir.join("validated-outcomes.tsv"), MAX_OUTCOME_LINES, MAX_STATE_FILE_BYTES).unwrap();
        let text = fs::read_to_string(dir.join("validated-outcomes.tsv")).unwrap();
        assert!(text.lines().count() <= MAX_OUTCOME_LINES);
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn recommendation_requires_evidence_in_current_context() {
        let dir = temp_state("recommend");
        let mut state = RuntimeState::new(&dir);
        let actions = r#"[{"id":"nic.ring.floor","applyScope":"device","applyTarget":"nic:pci:1","evaluationPaths":["path:lan-to-wan"],"risk":"safe"}]"#;
        handle_request(&observe_payload("h1", actions), &mut state, &test_config(&dir));
        for _ in 0..MIN_RECOMMENDATION_SAMPLES {
            handle_request(&outcome_payload("h1", "nic.ring.floor", 0.4, true), &mut state, &test_config(&dir));
        }
        let rec = state.recommendation_json();
        assert!(rec.contains("nic.ring.floor"));
        assert!(rec.contains("\"authority\":\"none\""));
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn context_drift_invalidates_stale_recommendation() {
        let dir = temp_state("drift");
        let cfg = test_config(&dir);
        let mut state = RuntimeState::new(&dir);
        let actions = r#"[{"id":"nic.ring.floor"}]"#;
        handle_request(&observe_payload("h1", actions), &mut state, &cfg);
        for _ in 0..MIN_RECOMMENDATION_SAMPLES {
            handle_request(&outcome_payload("h1", "nic.ring.floor", 0.4, true), &mut state, &cfg);
        }
        assert!(state.recommendation_json().contains("nic.ring.floor"));
        /* Capability hash change => new ContextKey => old evidence frozen. */
        handle_request(&observe_payload("h2", actions), &mut state, &cfg);
        assert_eq!(state.drift_events, 1);
        assert_eq!(state.recommendation_json(), "[]");
        assert!(fs::read_to_string(dir.join("decision-ledger.jsonl")).unwrap().contains("context_drift"));
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn legacy_outcome_file_lands_in_inert_partition() {
        let dir = temp_state("legacy");
        let legacy = format!("{}\ta\tcontrolled_ab\t0.5\ts\n", epoch_seconds());
        fs::write(dir.join("validated-outcomes.tsv"), legacy).unwrap();
        let state = RuntimeState::new(&dir);
        assert!(state.context_partitions.contains_key(LEGACY_CONTEXT));
        assert_eq!(state.outcomes, 1);
        assert!(!state.context_partitions.contains_key(&context_key("h1")));
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn state_survives_restart_within_same_partition() {
        let dir = temp_state("restart");
        let cfg = test_config(&dir);
        {
            let mut state = RuntimeState::new(&dir);
            handle_request(&outcome_payload("h1", "network.backlog", 0.25, true), &mut state, &cfg);
        }
        let mut reloaded = RuntimeState::new(&dir);
        handle_request(&observe_payload("h1", r#"[{"id":"network.backlog"}]"#), &mut reloaded, &cfg);
        for _ in 0..(MIN_RECOMMENDATION_SAMPLES - 1) {
            handle_request(&outcome_payload("h1", "network.backlog", 0.25, true), &mut reloaded, &cfg);
        }
        assert!(reloaded.recommendation_json().contains("network.backlog"));
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn rate_limit_rejects_flood() {
        let dir = temp_state("flood");
        let mut state = RuntimeState::new(&dir);
        let mut accepted = 0u32;
        let mut rejected = 0u32;
        for _ in 0..(MAX_REQUESTS_PER_SECOND + 5) {
            if state.permit() { accepted += 1; } else { rejected += 1; }
        }
        assert_eq!(accepted, MAX_REQUESTS_PER_SECOND);
        assert_eq!(rejected, 5);
        let _ = fs::remove_dir_all(dir);
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn wrong_peer_uid_is_rejected() {
        let euid = fs::metadata("/proc/self").unwrap().uid();
        if euid == 0 {
            /* Running as root cannot exercise the uid gate with a peer of the
             * same process; the boundary logic is still covered statically. */
            return;
        }
        let dir = temp_state("wrong-peer");
        let cfg = test_config(&dir);
        let mut state = RuntimeState::new(&dir);
        let (mut server, client) = UnixStream::pair().unwrap();
        handle_connection(client, &mut state, &cfg).unwrap();
        let mut reply = String::new();
        server.read_to_string(&mut reply).unwrap();
        assert!(reply.contains("peer-not-authorized"));
        assert_eq!(state.rejected, 1);
        assert_eq!(state.accepted, 0);
        let _ = fs::remove_dir_all(dir);
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn second_peer_gets_identical_boundary_treatment() {
        let euid = fs::metadata("/proc/self").unwrap().uid();
        if euid == 0 {
            return;
        }
        let dir = temp_state("second-peer");
        let cfg = test_config(&dir);
        let mut state = RuntimeState::new(&dir);
        for _ in 0..2 {
            let (mut server, client) = UnixStream::pair().unwrap();
            handle_connection(client, &mut state, &cfg).unwrap();
            let mut reply = String::new();
            server.read_to_string(&mut reply).unwrap();
            assert!(reply.contains("peer-not-authorized"));
        }
        assert_eq!(state.rejected, 2);
        assert_eq!(state.accepted, 0);
        let _ = fs::remove_dir_all(dir);
    }
}