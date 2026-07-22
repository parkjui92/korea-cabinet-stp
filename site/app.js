/* 과학기술정책 국무회의 아카이브 — 열람 화면.
 *
 * 분류(과기 판정·역할·태그)는 빌드 때 파이썬이 미리 계산해 번들에 구워 둔다.
 * 여기서 다시 판정하지 않는다 — 기준이 두 곳에 흩어지면 조용히 어긋난다.
 * 이 파일이 하는 일은 필터·검색·렌더링뿐이다.
 */

const PAGE = 200; // 한 번에 그릴 행 수. 1,000건 넘게 한꺼번에 그리면 버벅인다.

const el = (id) => document.getElementById(id);
const state = {
  data: null,
  meetingsByKey: new Map(),
  filtered: [],
  shown: 0,
};

// ── 로드 ────────────────────────────────────────────────────────────
async function boot() {
  const res = await fetch("data/bundle.json");
  if (!res.ok) throw new Error(`번들 로드 실패: ${res.status}`);
  state.data = await res.json();

  for (const m of state.data.meetings) state.meetingsByKey.set(m.key, m);

  renderMeta();
  fillSelects();
  bindEvents();
  apply();
}

function renderMeta() {
  const { meta } = state.data;
  el("metaRange").textContent = `· ${meta.range[0]} ~ ${meta.range[1]} · 회의 ${meta.meetings}회`;

  const roles = tally(state.data.agenda, (a) => a.role);
  el("stats").innerHTML = [
    stat(meta.agendaTotal.toLocaleString(), "전체 안건"),
    stat(meta.agendaStc.toLocaleString(), "과학기술정책 관련"),
    stat((roles.get("정책안건") || 0).toLocaleString(), "정책안건"),
    stat((roles.get("법률공포") || 0).toLocaleString(), "법률공포 (형식)"),
    stat(state.data.meetings.length.toLocaleString(), "회의"),
  ].join("");
}

const stat = (n, k) => `<div class="stat"><div class="n">${n}</div><div class="k">${k}</div></div>`;

function tally(rows, keyFn) {
  const m = new Map();
  for (const r of rows) {
    const k = keyFn(r);
    if (k) m.set(k, (m.get(k) || 0) + 1);
  }
  return m;
}

// ── 선택지 채우기 ───────────────────────────────────────────────────
function fillSelects() {
  // 소관: 실제로 안건이 있는 부처만, 건수 많은 순.
  const counts = tally(state.data.agenda, (a) => a.ministryId);
  const opts = [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([id, n]) => {
      const info = state.data.ministries[id];
      const mark = info?.core ? "★ " : "";
      return `<option value="${id}">${mark}${info?.name || id} (${n})</option>`;
    });
  el("ministry").insertAdjacentHTML("beforeend", opts.join(""));

  const tags = new Map();
  for (const a of state.data.agenda) for (const t of a.tags) tags.set(t, (tags.get(t) || 0) + 1);
  el("tag").insertAdjacentHTML(
    "beforeend",
    [...tags.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([t, n]) => `<option value="${t}">${t} (${n})</option>`)
      .join("")
  );
}

// ── 필터 ────────────────────────────────────────────────────────────
function apply() {
  const q = el("q").value.trim().toLowerCase();
  const [from, to] = (el("era").value || "|").split("|");
  const ministry = el("ministry").value;
  const tag = el("tag").value;
  const stcOnly = el("stcOnly").checked;
  const policyOnly = el("policyOnly").checked;

  state.filtered = state.data.agenda.filter((a) => {
    if (stcOnly && !a.stc) return false;
    if (policyOnly && a.role !== "정책안건") return false;
    if (ministry && a.ministryId !== ministry) return false;
    if (tag && !a.tags.includes(tag)) return false;
    if (from && a.date < from) return false;
    if (to && a.date > to) return false;
    if (q) {
      const hay = `${a.title} ${a.ministry} ${a.category}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  state.shown = 0;
  el("rows").innerHTML = "";
  renderHint();
  more();
}

function renderHint() {
  const n = state.filtered.length;
  const total = state.data.agenda.length;
  const stcOn = el("stcOnly").checked;
  const parts = [`<strong>${n.toLocaleString()}건</strong>`];
  if (n !== total) parts.push(`(전체 ${total.toLocaleString()}건 중)`);
  if (stcOn) parts.push("· 과학기술정책 관련만 보는 중입니다. 체크를 해제하면 전체가 나옵니다.");
  el("hint").innerHTML = parts.join(" ");
}

// ── 렌더 ────────────────────────────────────────────────────────────
function more() {
  const slice = state.filtered.slice(state.shown, state.shown + PAGE);
  el("rows").insertAdjacentHTML("beforeend", slice.map(row).join(""));
  state.shown += slice.length;

  el("more").hidden = state.shown >= state.filtered.length;
  el("shown").textContent = state.filtered.length
    ? `${state.shown.toLocaleString()} / ${state.filtered.length.toLocaleString()}`
    : "조건에 맞는 안건이 없습니다.";
}

function row(a) {
  const meeting = state.meetingsByKey.get(a.meetingKey);
  const badges = [];
  if (a.stc) badges.push(`<span class="tag ${a.core ? "core" : "adj"}">${a.stc}</span>`);
  for (const t of a.tags) badges.push(`<span class="tag topic">${esc(t)}</span>`);
  if (a.role !== "정책안건") badges.push(`<span class="tag role">${esc(a.role)}</span>`);

  // 판정 근거를 그대로 보여준다. 왜 잡혔는지 확인할 수 없는 라벨은 연구에 못 쓴다.
  const why = a.why
    ? `<div class="why-line">${esc(a.why)}</div>`
    : "";

  const title = meeting
    ? `<a href="${meeting.url}" target="_blank" rel="noreferrer noopener">${esc(a.title)}<span class="ext">↗</span></a>`
    : esc(a.title);

  return `<tr>
    <td class="c-date">${a.date}</td>
    <td class="c-sess">제${meeting?.session ?? "?"}회</td>
    <td class="c-cat">${esc(a.category)}</td>
    <td class="title">${title}${why}</td>
    <td class="c-min">${esc(a.ministry || "—")}</td>
    <td class="c-tag">${badges.join("")}</td>
  </tr>`;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

// ── 이벤트 ──────────────────────────────────────────────────────────
function bindEvents() {
  let timer;
  el("q").addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(apply, 180); // 16,742건을 매 타건마다 훑지 않는다
  });
  for (const id of ["era", "ministry", "tag", "stcOnly", "policyOnly"]) {
    el(id).addEventListener("change", apply);
  }
  el("more").addEventListener("click", more);
  el("reset").addEventListener("click", () => {
    el("q").value = "";
    el("era").value = "";
    el("ministry").value = "";
    el("tag").value = "";
    el("stcOnly").checked = true;
    el("policyOnly").checked = false;
    apply();
  });
}

boot().catch((err) => {
  el("hint").innerHTML = `<strong>데이터를 불러오지 못했습니다.</strong> ${esc(err.message)}`;
  console.error(err);
});
