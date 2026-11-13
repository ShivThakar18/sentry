/**
 * mock-core/server.ts: a fake Sentry core for UI development.
 *
 * Same URLs, same JSON, same WebSocket messages as docs/core-api.md, so the UI
 * can't tell it apart from the real core. It also serves the 🟡 draft sections
 * (groups, protocols, orders, home) that the real core doesn't have yet.
 *
 * Run:   npm run mock
 * Knobs (environment variables):
 *   MOCK_PORT=8001     port to listen on
 *   MOCK_DELAY=300     ms between "202 accepted" and the WS "device" update
 *   MOCK_CHAOS=0       turn OFF the Desk Plug flipping usable every 20 s
 *   MOCK_KICK=1        turn ON closing every WebSocket with 1013 every 30 s
 *
 * Plain Node `http` + the `ws` package, no framework, so all of it is visible.
 */
import http from "node:http";
import { WebSocket, WebSocketServer } from "ws";
import type {
  Capability,
  Device,
  Group,
  Limits,
  ValidationIssue,
  WsMessage,
} from "../src/api/contract";
import * as fixtures from "../src/mock/fixtures";

const PORT = Number(process.env.MOCK_PORT ?? 8001);
const DELAY_MS = Number(process.env.MOCK_DELAY ?? 300);
const CHAOS = process.env.MOCK_CHAOS !== "0";
const KICK = process.env.MOCK_KICK === "1";

// ===================================================================== //
// State: a private copy of the fixtures that we're free to change
// ===================================================================== //
// structuredClone = a deep copy. Without it we'd be editing the objects that
// fixtures.ts exports, which the UI's tests may also import.
const devices = new Map<string, Device>(structuredClone(fixtures.devices).map((d) => [d.id, d]));
const groups = new Map<string, Group>(structuredClone(fixtures.groups).map((g) => [g.id, g]));
const protocols = structuredClone(fixtures.protocols);
const orders = structuredClone(fixtures.orders);
const home = structuredClone(fixtures.home);

// ===================================================================== //
// WebSocket fan-out (the mock's version of the core's Hub)
// ===================================================================== //
const clients = new Set<WebSocket>();

function broadcast(msg: WsMessage): void {
  const text = JSON.stringify(msg);
  for (const ws of clients) {
    if (ws.readyState === WebSocket.OPEN) ws.send(text);
  }
}

function snapshot(): WsMessage {
  return {
    type: "snapshot",
    devices: [...devices.values()],
    // Draft keys. The real core doesn't send these yet (the UI must cope with
    // them missing: core-api.md §4.2 rule 1). Try deleting one to test that.
    groups: [...groups.values()],
    protocols,
    orders,
    home,
  };
}

// ===================================================================== //
// Command validation: the same checks, in the same order, as core/app/api.py
// ===================================================================== //
// set field → capability needed (mirrors core/app/capabilities.py)
const FIELD_TO_CAPABILITY: Record<string, Capability> = {
  on: "on_off",
  brightness: "brightness",
  color_xy: "color_xy",
  color_temp_k: "color_temp_k",
  target_temp_c: "target_temperature",
  mode: "hvac_mode",
};
// set field → its [min, max] key in `limits`
const FIELD_TO_RANGE: Record<string, keyof Limits> = {
  color_temp_k: "color_temp_k_range",
  target_temp_c: "target_temp_c_range",
};

type Cmd = Record<string, unknown>;

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/**
 * Step 1: the shape of the body, on its own (what Pydantic does in the core).
 * Returns FastAPI's LIST error form, so the UI has to handle both forms.
 */
function checkShape(body: unknown): ValidationIssue[] {
  const issue = (field: string, msg: string): ValidationIssue => ({
    loc: field ? ["body", field] : ["body"],
    msg,
    type: "value_error",
  });

  if (typeof body !== "object" || body === null || Array.isArray(body)) {
    return [issue("", "Input should be a JSON object")];
  }
  const cmd = body as Cmd;
  const fields = Object.keys(cmd);
  if (fields.length === 0) return [issue("", "empty command: send at least one field")];

  const issues: ValidationIssue[] = [];
  for (const f of fields) {
    const v = cmd[f];
    if (!(f in FIELD_TO_CAPABILITY)) issues.push(issue(f, "Extra inputs are not permitted"));
    else if (v === null) issues.push(issue(f, "fields can't be null"));
    else if (f === "on" && typeof v !== "boolean") issues.push(issue(f, "Input should be a valid boolean"));
    else if (f === "brightness" && !(isNum(v) && v > 0 && v <= 100))
      issues.push(issue(f, "brightness must be a number, 0 < x ≤ 100 (use on:false for off)"));
    else if (f === "color_temp_k" && !Number.isInteger(v)) issues.push(issue(f, "Input should be a valid integer"));
    else if (f === "target_temp_c" && !isNum(v)) issues.push(issue(f, "Input should be a valid number"));
    else if (f === "mode" && !["heat", "cool", "auto", "off"].includes(v as string))
      issues.push(issue(f, "Input should be 'heat', 'cool', 'auto' or 'off'"));
    else if (f === "color_xy") {
      const xy = v as Record<string, unknown>;
      const ok =
        typeof v === "object" && Object.keys(xy).sort().join() === "x,y" &&
        isNum(xy.x) && isNum(xy.y) && xy.x >= 0 && xy.x <= 1 && xy.y >= 0 && xy.y <= 1;
      if (!ok) issues.push(issue(f, "color_xy must be {x, y}, each 0–1"));
    }
  }
  if ("color_xy" in cmd && "color_temp_k" in cmd) {
    issues.push(issue("", "send color_xy or color_temp_k, not both"));
  }
  return issues;
}

/** Steps 2–3: can THIS target do it, and is every value in ITS range? (string error form) */
function checkFor(
  target: { name: string; capabilities: Capability[]; limits: Limits },
  cmd: Cmd,
): string | null {
  const unsupported = Object.keys(cmd).filter((f) => !target.capabilities.includes(FIELD_TO_CAPABILITY[f]));
  if (unsupported.length) return `${target.name} doesn't support: ${unsupported.join(", ")}`;

  for (const [field, key] of Object.entries(FIELD_TO_RANGE)) {
    const range = target.limits[key];
    if (field in cmd && range) {
      const [lo, hi] = range;
      const v = cmd[field] as number;
      if (v < lo || v > hi) return `${field} must be between ${lo} and ${hi} for ${target.name}`;
    }
  }
  return null;
}

// ===================================================================== //
// Pretending to be the adapters: apply a command after a delay
// ===================================================================== //
function applyToDevice(id: string, cmd: Cmd): void {
  const dev = devices.get(id);
  if (!dev) return;
  const state = { ...dev.state, ...cmd };
  // A light is in colour mode OR white mode (core-api.md §2.1): setting one
  // clears the other, exactly like a real Hue bulb reports it.
  if ("color_xy" in cmd) state.color_temp_k = null;
  if ("color_temp_k" in cmd) state.color_xy = null;
  dev.state = state;
  broadcast({ type: "device", device: dev }); // full object, never a patch (§4.2 rule 2)
  refreshGroupsContaining(id);
}

/** Recompute a group's state from its members (core-api.md §6.1 rules). */
function computeGroup(g: Group): void {
  const members = g.members.map((id) => devices.get(id)).filter((d): d is Device => !!d);
  const usable = members.filter((d) => d.usable);
  const lit = usable.filter((d) => d.state.on);
  const same = <T,>(values: T[]): T | null =>
    values.length && values.every((v) => JSON.stringify(v) === JSON.stringify(values[0])) ? values[0] : null;

  g.usable = usable.length > 0;
  g.state = {
    on: lit.length > 0,
    members_on: lit.length,
    // Average brightness of the lit members; left out entirely when none are lit.
    ...(lit.length
      ? { brightness: Math.round(lit.reduce((sum, d) => sum + (d.state.brightness ?? 0), 0) / lit.length) }
      : {}),
    color_temp_k: same(lit.map((d) => d.state.color_temp_k ?? null)),
    color_xy: same(lit.map((d) => d.state.color_xy ?? null)),
  };
}

function refreshGroupsContaining(deviceId: string): void {
  for (const g of groups.values()) {
    if (g.members.includes(deviceId)) {
      computeGroup(g);
      broadcast({ type: "group", group: g });
    }
  }
}

// ===================================================================== //
// HTTP
// ===================================================================== //
type Res = http.ServerResponse;

function reply(res: Res, status: number, body?: unknown): void {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(body === undefined ? "" : JSON.stringify(body));
}

async function readJson(req: http.IncomingMessage): Promise<unknown> {
  let raw = "";
  for await (const chunk of req) raw += chunk; // a request body arrives in pieces
  return raw ? JSON.parse(raw) : undefined;    // throws on bad JSON; caller turns that into 422
}

async function handle(req: http.IncomingMessage, res: Res): Promise<number> {
  const method = req.method ?? "GET";
  const path = new URL(req.url ?? "/", "http://mock").pathname;
  let m: RegExpMatchArray | null;

  // ---- devices (✅ in the real core) ------------------------------------
  if (method === "GET" && path === "/api/devices") {
    reply(res, 200, [...devices.values()]);
    return 200;
  }
  if (method === "GET" && (m = path.match(/^\/api\/devices\/([^/]+)$/))) {
    const dev = devices.get(m[1]);
    if (!dev) return fail(res, 404, `unknown device '${m[1]}'`);
    reply(res, 200, dev);
    return 200;
  }
  if (method === "POST" && (m = path.match(/^\/api\/devices\/([^/]+)\/set$/))) {
    const body = await readJson(req);
    const shape = checkShape(body);
    if (shape.length) return failList(res, shape);
    const cmd = body as Cmd;
    const dev = devices.get(m[1]);
    if (!dev) return fail(res, 404, `unknown device '${m[1]}'`);
    const bad = checkFor(dev, cmd);
    if (bad) return fail(res, 422, bad);
    if (!dev.usable) return fail(res, 409, `${dev.name} is unavailable (adapter offline or device unreachable)`);

    reply(res, 202, { accepted: cmd });
    // 202 now, the real change LATER. This gap is what the optimistic UI (6g) covers.
    setTimeout(() => applyToDevice(dev.id, cmd), DELAY_MS);
    return 202;
  }

  // ---- groups (🟡 draft) ---------------------------------------------------
  if (method === "GET" && path === "/api/groups") {
    reply(res, 200, [...groups.values()]);
    return 200;
  }
  if (method === "POST" && (m = path.match(/^\/api\/groups\/([^/]+)\/set$/))) {
    const body = await readJson(req);
    const shape = checkShape(body);
    if (shape.length) return failList(res, shape);
    const cmd = body as Cmd;
    const g = groups.get(m[1]);
    if (!g) return fail(res, 404, `unknown group '${m[1]}'`);
    const bad = checkFor(g, cmd);
    if (bad) return fail(res, 422, bad);

    const sent_to: string[] = [];
    const skipped: { id: string; reason: string }[] = [];
    for (const id of g.members) {
      if (devices.get(id)?.usable) sent_to.push(id);
      else skipped.push({ id, reason: "unavailable" });
    }
    if (sent_to.length === 0) return fail(res, 409, `${g.name}: no member is available`);

    reply(res, 202, { accepted: cmd, sent_to, skipped });
    // Real bulbs don't all answer at the same moment. Stagger them a little,
    // so the UI sees the group's state settle one member at a time.
    sent_to.forEach((id, i) => setTimeout(() => applyToDevice(id, cmd), DELAY_MS + i * 60));
    return 202;
  }

  // ---- read-only drafts --------------------------------------------------
  if (method === "GET" && path === "/api/protocols") return ok(res, protocols);
  if (method === "GET" && path === "/api/orders") return ok(res, orders);
  if (method === "GET" && path === "/api/home") return ok(res, home);

  // FastAPI's answer for a route that doesn't exist.
  return fail(res, 404, "Not Found");
}

function ok(res: Res, body: unknown): number {
  reply(res, 200, body);
  return 200;
}
function fail(res: Res, status: number, detail: string): number {
  reply(res, status, { detail });
  return status;
}
function failList(res: Res, detail: ValidationIssue[]): number {
  reply(res, 422, { detail });
  return 422;
}

const server = http.createServer((req, res) => {
  handle(req, res)
    .then((status) => console.log(`${req.method} ${req.url} → ${status}`))
    .catch((err: unknown) => {
      // The only expected throw is JSON.parse on a broken body.
      const msg = err instanceof SyntaxError ? "body is not valid JSON" : String(err);
      failList(res, [{ loc: ["body"], msg, type: "json_invalid" }]);
      console.log(`${req.method} ${req.url} → 422 (${msg})`);
    });
});

// ===================================================================== //
// WebSocket endpoint
// ===================================================================== //
// Shares the HTTP server's port. Only upgrade requests to /api/ws reach it.
const wss = new WebSocketServer({ server, path: "/api/ws" });

wss.on("connection", (ws) => {
  clients.add(ws);
  console.log(`ws connected (${clients.size} open)`);
  ws.send(JSON.stringify(snapshot())); // always the first message (§4.1)
  ws.on("close", () => {
    clients.delete(ws);
    console.log(`ws disconnected (${clients.size} open)`);
  });
  // Like the real core: whatever the UI sends is ignored.
});

// ===================================================================== //
// Chaos: things a real house does, on a timer
// ===================================================================== //
if (CHAOS) {
  setInterval(() => {
    const desk = devices.get("tuya-desk");
    if (!desk) return;
    desk.usable = !desk.usable;
    desk.state = { ...desk.state, available: desk.usable };
    console.log(`chaos: Desk Plug usable=${desk.usable}`);
    broadcast({ type: "device", device: desk });
  }, 20_000);
}

if (KICK) {
  setInterval(() => {
    if (clients.size === 0) return;
    console.log(`kick: closing ${clients.size} socket(s) with 1013`);
    for (const ws of clients) ws.close(1013, "try again later"); // the core's "you fell behind"
  }, 30_000);
}

for (const g of groups.values()) computeGroup(g); // start consistent with the members

server.listen(PORT, () => {
  console.log(`mock core on http://localhost:${PORT}  (delay ${DELAY_MS} ms, chaos ${CHAOS ? "on" : "off"}, kick ${KICK ? "on" : "off"})`);
});
