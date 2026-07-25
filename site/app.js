/* 과학기술정책 국무회의 아카이브 — 열람 화면.
 *
 * 분류(과기 판정·역할·태그)는 빌드 때 파이썬이 미리 계산해 번들에 구워 둔다.
 * 여기서 다시 판정하지 않는다 — 기준이 두 곳에 흩어지면 조용히 어긋난다.
 * 이 파일이 하는 일은 필터·검색·렌더링뿐이다.
 *
 * 교차 검색: 검색어는 안건 제목과 발언 전문을 동시에 훑는다. 발언에서 맞으면
 * "그 회의 안건 보기"로 같은 회차의 의결 안건을 펼쳐 볼 수 있다 — 이게 이
 * 아카이브의 핵심 동작이다("대통령이 X 발언한 회의에 무엇이 의결됐나").
 */

const PAGE = 200; // 한 번에 그릴 행 수. 1,000건 넘게 한꺼번에 그리면 버벅인다.
const UTT_MAX = 40; // 발언 검색 결과 표시 상한. 전문이 길어 많이 그리면 무겁다.

const el = (id) => document.getElementById(id);
const state = {
  data: null,
  meetingsByKey: new Map(),
  filtered: [],
  shown: 0,
  meetingFilter: null, // 회의 드릴다운. 설정되면 그 회차의 안건만, stcOnly 무시.
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
    stat(state.data.utterances.length.toLocaleString(), "대통령·국무위원 발언"),
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
  const mf = state.meetingFilter;

  state.filtered = state.data.agenda.filter((a) => {
    // 회의 드릴다운이 걸리면 그 회차 전부를 보여준다(그날 무엇이 의결됐나가 요점).
    if (mf) return a.meetingKey === mf;
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
  renderUtterances(q);
  renderMeetingBar();
  renderHint();
  more();
}

// ── 발언 교차 검색 ──────────────────────────────────────────────────
function renderUtterances(q) {
  const box = el("utterances");
  // 드릴다운 중이거나 검색어가 2글자 미만이면 발언 패널을 숨긴다.
  if (state.meetingFilter || q.length < 2) {
    box.hidden = true;
    box.innerHTML = "";
    return;
  }

  const hits = state.data.utterances.filter((u) => u.text.toLowerCase().includes(q));
  if (!hits.length) {
    box.hidden = true;
    box.innerHTML = "";
    return;
  }

  const shown = hits.slice(0, UTT_MAX);
  const rows = shown
    .map((u) => {
      const m = state.meetingsByKey.get(u.meetingKey);
      const snippet = snippetAround(u.text, q);
      return `<li>
        <div class="u-head">
          <span class="u-date">${u.date}</span>
          <span class="u-who">${esc(u.speaker)}</span>
          <button type="button" class="u-jump" data-meeting="${u.meetingKey}">제${m?.session ?? "?"}회 의결 안건 보기 →</button>
        </div>
        <div class="u-text">${snippet}</div>
      </li>`;
    })
    .join("");

  box.hidden = false;
  box.innerHTML = `
    <div class="u-title">
      🎙 발언에서 <strong>${hits.length.toLocaleString()}건</strong> 찾음
      ${hits.length > UTT_MAX ? `<span class="muted">(상위 ${UTT_MAX}건 표시)</span>` : ""}
    </div>
    <ul class="u-list">${rows}</ul>`;
}

function snippetAround(text, q) {
  const i = text.toLowerCase().indexOf(q);
  if (i < 0) return esc(text.slice(0, 160));
  const start = Math.max(0, i - 60);
  const end = Math.min(text.length, i + q.length + 100);
  const pre = start > 0 ? "…" : "";
  const post = end < text.length ? "…" : "";
  return (
    pre +
    esc(text.slice(start, i)) +
    `<mark>${esc(text.slice(i, i + q.length))}</mark>` +
    esc(text.slice(i + q.length, end)) +
    post
  );
}

// ── 회의 드릴다운 표시줄 ────────────────────────────────────────────
function renderMeetingBar() {
  const bar = el("meetingBar");
  if (!state.meetingFilter) {
    bar.hidden = true;
    bar.innerHTML = "";
    return;
  }
  const m = state.meetingsByKey.get(state.meetingFilter);
  bar.hidden = false;
  bar.innerHTML = `
    <span>제${m?.session ?? "?"}회 국무회의 (${m?.date ?? ""}) 의결 안건 전체를 보는 중</span>
    <a href="${m?.url ?? "#"}" target="_blank" rel="noreferrer noopener">원문 ↗</a>
    <button type="button" id="clearMeeting" class="ghost">← 검색으로 돌아가기</button>`;
  el("clearMeeting").addEventListener("click", () => {
    state.meetingFilter = null;
    apply();
  });
}

function renderHint() {
  const n = state.filtered.length;
  const total = state.data.agenda.length;
  const parts = [`<strong>${n.toLocaleString()}건</strong>`];
  if (state.meetingFilter) {
    parts.push("· 이 회의의 안건 전부입니다(과기 필터 무시).");
  } else {
    if (n !== total) parts.push(`(전체 ${total.toLocaleString()}건 중)`);
    if (el("stcOnly").checked) parts.push("· 과학기술정책 관련만 보는 중입니다. 체크를 해제하면 전체가 나옵니다.");
  }
  el("hint").innerHTML = parts.join(" ");
}

// ── 안건 렌더 ───────────────────────────────────────────────────────
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

  const why = a.why ? `<div class="why-line">${esc(a.why)}</div>` : "";
  const title = meeting
    ? `<a href="${meeting.url}" target="_blank" rel="noreferrer noopener">${esc(a.title)}<span class="ext">↗</span></a>`
    : esc(a.title);
  // 드릴다운이 아닐 때만 회차를 클릭 가능하게 — 그 회의로 파고들 수 있다.
  const sess = state.meetingFilter
    ? `제${meeting?.session ?? "?"}회`
    : `<button type="button" class="sess-jump" data-meeting="${a.meetingKey}">제${meeting?.session ?? "?"}회</button>`;

  return `<tr>
    <td class="c-date">${a.date}</td>
    <td class="c-sess">${sess}</td>
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

function drillTo(meetingKey) {
  state.meetingFilter = meetingKey;
  apply();
  document.querySelector(".tablewrap")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ── CSV 내려받기 ────────────────────────────────────────────────────
// 화면에 필터 건 그대로(state.filtered) 내보낸다. 연구자가 R·엑셀로 바로
// 가져갈 수 있게 원문 링크·판정근거까지 포함한다. 분류값은 이미 계산돼 있다.
function csvCell(v) {
  const s = v == null ? "" : Array.isArray(v) ? v.join("; ") : String(v);
  // 쉼표·따옴표·줄바꿈이 있으면 따옴표로 감싸고 내부 따옴표는 이중화.
  return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

function downloadCsv() {
  const cols = [
    ["개최일", (a) => a.date],
    ["회차", (a) => state.meetingsByKey.get(a.meetingKey)?.session],
    ["의안번호", (a) => a.billNo],
    ["유형", (a) => a.category],
    ["안건명", (a) => a.title],
    ["소관", (a) => a.ministry],
    ["소관ID", (a) => a.ministryId],
    ["역할", (a) => a.role],
    ["과기정책", (a) => (a.stc ? a.stc : "무관")],
    ["주제태그", (a) => a.tags],
    ["판정근거", (a) => a.why],
    ["의결결과", (a) => a.cabinetResult],
    ["원문링크", (a) => state.meetingsByKey.get(a.meetingKey)?.url],
  ];

  const header = cols.map((c) => c[0]).join(",");
  const lines = state.filtered.map((a) => cols.map((c) => csvCell(c[1](a))).join(","));
  // BOM을 앞에 붙여야 엑셀이 UTF-8 한글을 깨지 않고 연다.
  const blob = new Blob(["﻿" + header + "\n" + lines.join("\n")], {
    type: "text/csv;charset=utf-8",
  });

  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = csvFilename();
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function csvFilename() {
  // 파일명에 필터 상태를 담아, 여러 번 받아도 뭘 받았는지 알 수 있게.
  const parts = ["국무회의_안건"];
  if (state.meetingFilter) parts.push(state.meetingFilter);
  else {
    if (el("stcOnly").checked) parts.push("과기정책");
    if (el("policyOnly").checked) parts.push("정책안건");
    const mid = el("ministry").value;
    if (mid) parts.push(state.data.ministries[mid]?.name || mid);
    const tag = el("tag").value;
    if (tag) parts.push(tag);
    const q = el("q").value.trim();
    if (q) parts.push(q.replace(/[^\w가-힣]/g, ""));
  }
  parts.push(`${state.filtered.length}건`);
  return parts.join("_") + ".csv";
}

// ── 이벤트 ──────────────────────────────────────────────────────────
function bindEvents() {
  let timer;
  el("q").addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(apply, 180);
  });
  for (const id of ["era", "ministry", "tag", "stcOnly", "policyOnly"]) {
    el(id).addEventListener("change", () => {
      state.meetingFilter = null; // 필터를 만지면 드릴다운을 푼다
      apply();
    });
  }
  el("more").addEventListener("click", more);
  el("csv").addEventListener("click", downloadCsv);

  // 발언 패널·안건 표의 "회의로 가기" 버튼은 이벤트 위임으로 한 번에.
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-meeting]");
    if (btn) drillTo(btn.dataset.meeting);
  });

  el("reset").addEventListener("click", () => {
    el("q").value = "";
    el("era").value = "";
    el("ministry").value = "";
    el("tag").value = "";
    el("stcOnly").checked = true;
    el("policyOnly").checked = false;
    state.meetingFilter = null;
    apply();
  });
}

boot().catch((err) => {
  el("hint").innerHTML = `<strong>데이터를 불러오지 못했습니다.</strong> ${esc(err.message)}`;
  console.error(err);
});
