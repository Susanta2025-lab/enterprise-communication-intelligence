/*
 * PROPOSAL ONLY — no invocation, authentication discovery, or network at load time.
 * Ordinary Chrome DevTools cannot access the application's lexical MSAL/provider
 * objects. Pasting this file alone does NOT supply authenticated execution.
 *
 * Separately authorized minimal integration: in the existing frontend composition
 * scope, retain the existing MsalAccessTokenProvider in a local variable shared
 * with EciApiClient; pass it, the SAME msalInstance, and config.apiBaseUrl here.
 * Keep the returned one-shot runner private and bind it to an operator-only button
 * enabled after MSAL interaction completes. Do not expose auth handles on window,
 * import a second MSAL instance, inspect React internals, or extract stored tokens.
 * That source/build/deployment work is NOT implemented or authorized by this file.
 *
 * Before clicking: obtain separate execution authorization, review this file and
 * the report, verify current read-only preflight/identity evidence, and ensure no
 * previous fixture execution or other tab is running it. Preserve only sanitized
 * console evidence. Do not export Network/HAR, headers, claims, or full responses.
 * Closing/reloading the page does not authorize restarting an interrupted run.
 */
"use strict";
function createPhase22GValidation({ tokenProvider, msalInstance, apiBaseUrl }) {
  const ORIGIN = "https://dnookm0ucbhv1.cloudfront.net";
  const ROOT = "/api/v1/work-items";
  const CREATE = '{"creation_key":"phase22g-20260928-3d55c464-c7cf-4752-b45f-6bc5d9885a65","kind":"action","title":"SYNTHETIC Phase 22G 3d55c464-c7cf-4752-b45f-6bc5d9885a65","description":null,"due":{"kind":"none"},"business_context_id":null,"sources":[]}';
  const STEPS = [
    ["W1", "", CREATE, 201, 1, "open"],
    ["W2", "", CREATE, 200, 1, "open"],
    ["W3", "status", '{"expected_version":1,"status":"in_progress","reopen":false}', 200, 2, "in_progress"],
    ["W4", "status", '{"expected_version":2,"status":"completed","reopen":false}', 200, 3, "completed"],
    ["W5", "status", '{"expected_version":3,"status":"open","reopen":true}', 200, 4, "open"],
    ["W6", "status", '{"expected_version":4,"status":"cancelled","reopen":false}', 200, 5, "cancelled"],
    ["W7", "archive", '{"expected_version":5}', 200, 6, "cancelled"],
    ["W8", "restore", '{"expected_version":6}', 200, 7, "cancelled"],
  ];
  const uuid = value => typeof value === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
  const fail = code => { throw new Error(code); }; // Only script-owned codes.
  const check = (ok, code) => { if (!ok) fail(code); };
  const canonical = value => JSON.stringify(value, function (_key, child) {
    return child && typeof child === "object" && !Array.isArray(child)
      ? Object.fromEntries(Object.entries(child).sort(([a], [b]) => a.localeCompare(b))) : child;
  });
  const equal = (a, b) => canonical(a) === canonical(b);
  const keys = (object, names) => equal(Object.keys(object).sort(), names.split(" ").sort());
  const time = value => typeof value === "string" && /T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));
  const itemKeys = "id kind title description due business_context_id status completed_at cancelled_at archived_at created_at updated_at version creation_origin confirmed_at overdue";
  let used = false;
  let itemId = null; // Assigned only from W1; never replaced.
  let identity = null;
  let previous = null;
  let history = [];
  let creationLocation = null;
  let step = "preflight";
  let lastVerified = null;
  let uncertain = false;
  let stopCode = "INTERNAL_CHECK_FAILED";
  const emit = record => console.info("Phase22G", JSON.stringify({ utc: new Date().toISOString(), ...record }));
  const guard = (ok, code) => { stopCode = code; check(ok, code); };
  // Account metadata stays in memory; never emit identifiers or claims.
  function accountKey() {
    const account = msalInstance.getActiveAccount();
    guard(account !== null, "NO_EXPLICIT_ACTIVE_ACCOUNT");
    guard([account.homeAccountId, account.localAccountId, account.tenantId, account.environment]
      .every(value => typeof value === "string" && value.length > 0), "ACCOUNT_METADATA_MISSING");
    return canonical([account.homeAccountId, account.localAccountId, account.tenantId, account.environment]);
  }
  function sameAccount() { guard(accountKey() === identity, "ACCOUNT_CHANGED"); }

  async function request(method, path, body, expected, reconcile = false) {
    const url = new URL(path, ORIGIN);
    const detail = itemId === null ? null : `${ROOT}/${itemId}`;
    const allowedReads = detail === null ? [] : [detail, `${detail}/events?limit=100&offset=0`, `${detail}/events?limit=100&offset=7`];
    const planned = STEPS.find(entry => entry[0] === step);
    const plannedPath = planned ? (planned[1] ? `${detail}/${planned[1]}` : ROOT) : null;
    guard(url.origin === ORIGIN && url.protocol === "https:" && url.href === ORIGIN + path &&
      !url.username && !url.password && !url.hash, "DESTINATION_REJECTED");
    guard(method === "GET" ? allowedReads.includes(path) && body === undefined :
      method === "POST" && !reconcile && !uncertain && planned && path === plannedPath && body === planned[2], "REQUEST_NOT_ALLOWLISTED");
    sameAccount();
    stopCode = "AUTHENTICATION_FAILED";
    let token = await tokenProvider.acquireAccessToken(); // Existing provider; silent only.
    guard(typeof token === "string" && token.length > 0, "AUTHENTICATION_FAILED");
    sameAccount();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);
    let response;
    try {
      if (method === "POST") uncertain = true;
      stopCode = method === "POST" ? "POST_OUTCOME_UNCERTAIN" : "READ_FAILED";
      response = await fetch(url.href, {
        method, body, signal: controller.signal, redirect: "error",
        mode: "cors", credentials: "omit", cache: "no-store", referrerPolicy: "no-referrer",
        headers: { Accept: "application/json", Authorization: `Bearer ${token}`,
          ...(method === "POST" ? { "Content-Type": "application/json" } : {}) },
      });
      token = null;
      guard(!response.redirected && response.url === url.href, "RESPONSE_DESTINATION_REJECTED");
      emit({ step, method, path, http: response.status });
      // W1 replay is exceptional: read its UUID solely for owned reconciliation,
      // then stop. Never execute W2 or create a replacement fixture.
      const existing = step === "W1" && method === "POST" && response.status === 200;
      guard(response.status === expected || existing, "UNEXPECTED_HTTP_STATUS");
      stopCode = method === "POST" ? "POST_RESPONSE_UNREADABLE" : "READ_RESPONSE_UNREADABLE";
      const data = await response.json();
      if (step === "W1" && method === "POST") {
        guard(itemId === null && uuid(data.id), "W1_UUID_INVALID");
        itemId = data.id;
        emit({ step, fixture_id: itemId }); // Preserve exact synthetic UUID for review.
      }
      if (existing) { fail("FIXTURE_MAY_ALREADY_EXIST"); }
      sameAccount();
      if (method === "POST") uncertain = false;
      return { data, location: response.headers.get("Location") };
    } finally {
      token = null;
      clearTimeout(timer);
    }
  }

  function validateItem(item, version, status, detail) {
    guard(keys(item, itemKeys + (detail ? " sources" : "")), "ITEM_FIELDS_MISMATCH");
    guard(item.id === itemId && item.version === version && item.status === status, "ITEM_STATE_MISMATCH");
    const fixture = JSON.parse(CREATE);
    guard(item.kind === fixture.kind && item.title === fixture.title && item.description === null &&
      equal(item.due, { kind: "none" }) && item.business_context_id === null &&
      item.creation_origin === "manual" && item.confirmed_at === null && item.overdue === false,
    "FIXTURE_FIELDS_MISMATCH");
    if (detail) guard(equal(item.sources, []), "SOURCES_NOT_EMPTY");
    guard(time(item.created_at) && time(item.updated_at) && Date.parse(item.updated_at) >= Date.parse(item.created_at), "ITEM_TIME_INVALID");
    guard(status === "completed" ? time(item.completed_at) && item.completed_at === item.updated_at : item.completed_at === null, "COMPLETION_TIME_MISMATCH");
    guard(status === "cancelled" ? time(item.cancelled_at) : item.cancelled_at === null, "CANCELLATION_TIME_MISMATCH");
    if (version === 5) guard(item.cancelled_at === item.updated_at, "CANCELLATION_UPDATE_MISMATCH");
    guard(version === 6 ? time(item.archived_at) && item.archived_at === item.updated_at : item.archived_at === null, "ARCHIVE_TIME_MISMATCH");
    if (previous) {
      guard(item.created_at === previous.created_at && Date.parse(item.updated_at) >= Date.parse(previous.updated_at), "TIMESTAMP_CHANGED_UNEXPECTEDLY");
      if (version > 5) guard(item.cancelled_at === previous.cancelled_at, "CANCELLATION_TIME_CHANGED");
    }
  }

  function validateHistory(page, item) {
    guard(keys(page, "items limit offset") && page.limit === 100 && page.offset === 0 &&
      Array.isArray(page.items) && page.items.length === item.version, "HISTORY_COUNT_MISMATCH");
    const types = ["created", "status_changed", "status_changed", "status_changed", "status_changed", "archived", "restored"];
    const statuses = ["open", "in_progress", "completed", "open", "cancelled"];
    const ids = new Set();
    page.items.forEach((event, index) => {
      guard(keys(event, "id work_item_id event_type occurred_at item_version event_ordinal context_at_event_id metadata"), "EVENT_FIELDS_MISMATCH");
      guard(uuid(event.id) && !ids.has(event.id) && event.work_item_id === itemId &&
        event.item_version === index + 1 && event.event_ordinal === 0 && event.context_at_event_id === null &&
        event.event_type === types[index] && time(event.occurred_at), "EVENT_MISMATCH");
      ids.add(event.id);
      const metadata = index === 0 ? { status: "open", due: { kind: "none" }, creation_origin: "manual" } :
        index < 5 ? { old_status: statuses[index - 1], new_status: statuses[index] } : {};
      guard(equal(event.metadata, metadata), "EVENT_METADATA_MISMATCH");
      if (index < history.length) guard(equal(event, history[index]), "EXISTING_EVENT_CHANGED");
    });
    guard(page.items[0].occurred_at === item.created_at && page.items.at(-1).occurred_at === item.updated_at, "EVENT_TIME_MISMATCH");
  }

  async function verify(post, version, status) {
    validateItem(post.data, version, status, false);
    const detail = (await request("GET", `${ROOT}/${itemId}`, undefined, 200)).data;
    validateItem(detail, version, status, true);
    const { sources: _sources, ...fields } = detail;
    guard(equal(fields, post.data), "POST_DETAIL_MISMATCH");
    const page = (await request("GET", `${ROOT}/${itemId}/events?limit=100&offset=0`, undefined, 200)).data;
    validateHistory(page, detail);
    if (step === "W2") guard(equal(detail, previous) && equal(page.items, history), "REPLAY_CHANGED_ITEM_OR_EVENTS");
    previous = detail;
    history = page.items;
    lastVerified = { step, version, status, archived: detail.archived_at !== null, event_count: history.length, source_count: 0 };
    emit({ ...lastVerified, result: "PASS" });
  }

  async function reconcile() {
    // No creation-key GET exists. Do not enumerate unrelated items or replay W1.
    if (itemId === null) { emit({ result: "RECONCILIATION_UNAVAILABLE_NO_UUID" }); return; }
    try {
      const detail = (await request("GET", `${ROOT}/${itemId}`, undefined, 200, true)).data;
      const page = (await request("GET", `${ROOT}/${itemId}/events?limit=100&offset=0`, undefined, 200, true)).data;
      guard(Number.isInteger(detail.version) && detail.version >= 1 && detail.version <= 7, "RECONCILIATION_VERSION_INVALID");
      const status = ["open", "in_progress", "completed", "open", "cancelled", "cancelled", "cancelled"][detail.version - 1];
      validateItem(detail, detail.version, status, true);
      validateHistory(page, detail);
      emit({ result: "READ_ONLY_RECONCILIATION_REVIEW_REQUIRED", version: detail.version, status,
        archived: detail.archived_at !== null, event_count: page.items.length, source_count: 0 });
    } catch { emit({ result: "READ_ONLY_RECONCILIATION_UNVERIFIED" }); }
    // Deliberately no resume path, even if reconciliation matches expectations.
  }

  return async function runPhase22GOnce() {
    if (used) { emit({ result: "STOP_ALREADY_ATTEMPTED" }); return; }
    used = true; // Set before prompts and awaits; concurrent clicks cannot reenter.
    try {
      guard(apiBaseUrl === ORIGIN && globalThis.location?.protocol === "https:", "ENVIRONMENT_NOT_APPROVED");
      guard(typeof tokenProvider?.acquireAccessToken === "function" && typeof msalInstance?.getActiveAccount === "function", "AUTH_INTEGRATION_MISSING");
      identity = accountKey();
      guard(window.confirm("Phase 22G: Confirm SEPARATE execution authorization, reviewed script/report, completed read-only preflight, approved API origin, ECS revision 14 and schema 22b0001 evidence, same existing mapped Entra identity used for successful listing/Candidates, MSAL idle, no previous fixture attempt and no concurrent operator/tab. Cancel if any prerequisite is uncertain."), "PREFLIGHT_NOT_CONFIRMED");
      for (const [name, operation, body, expected, version, status] of STEPS) {
        step = name;
        const path = operation ? `${ROOT}/${itemId}/${operation}` : ROOT;
        guard(window.confirm(`${name}: authorize ONE POST to ${ORIGIN}${path}\n${body}\nExpected HTTP ${expected}, version ${version}, status ${status}. Cancel stops permanently. No automatic retry.`), "OPERATOR_CANCELLED");
        const post = await request("POST", path, body, expected);
        if (name === "W1" || name === "W2") {
          guard(post.location === `${ROOT}/${itemId}`, "CREATION_LOCATION_MISSING_OR_WRONG");
          if (name === "W1") creationLocation = post.location;
          else guard(post.location === creationLocation, "REPLAY_LOCATION_CHANGED");
        }
        await verify(post, version, status);
      }
      const tail = (await request("GET", `${ROOT}/${itemId}/events?limit=100&offset=7`, undefined, 200)).data;
      guard(keys(tail, "items limit offset") && tail.limit === 100 && tail.offset === 7 && equal(tail.items, []), "HISTORY_TAIL_NOT_EMPTY");
      emit({ result: "W1_W8_API_ASSERTIONS_PASS", ...lastVerified });
    } catch (error) {
      const code = error instanceof Error && error.message === "FIXTURE_MAY_ALREADY_EXIST" ? "FIXTURE_MAY_ALREADY_EXIST" : stopCode;
      emit({ step, result: "STOP_OPERATOR_REVIEW_REQUIRED", code, last_verified: lastVerified });
      if (uncertain || code === "FIXTURE_MAY_ALREADY_EXIST") await reconcile();
    }
  };
}
