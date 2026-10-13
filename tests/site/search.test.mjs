/* site/app.js 검색 동작 회귀 테스트.
 *
 * 이 버그들은 순수함수가 아니라 "이벤트 배선"에 있었다(검색창 입력이 드릴다운을
 * 풀지 않음). 그래서 필터 로직만 떼어내 검사하면 못 잡는다. 최소 DOM 스텁을 깔고
 * 실제 site/app.js를 그대로 구동해, 사용자가 하는 순서대로 눌러 본다.
 *
 * 실행: node --test tests/site/
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const APP = fileURLToPath(new URL("../../site/app.js", import.meta.url));

// ── 최소 DOM 스텁 ───────────────────────────────────────────────────
// app.js가 실제로 부르는 것만 구현한다. innerHTML은 문자열로만 둔다 —
// 렌더 결과는 문자열로 검사하는 편이 오히려 직접적이다.
class El {
  constructor(id) {
    this.id = id;
    this.innerHTML = "";
    this.textContent = "";
    this.hidden = false;
    this.value = "";
    this.checked = false;
    this._handlers = new Map();
  }
  addEventListener(type, fn) {
    if (!this._handlers.has(type)) this._handlers.set(type, []);
    this._handlers.get(type).push(fn);
  }
  insertAdjacentHTML(_pos, html) {
    this.innerHTML += html;
  }
  dispatch(type) {
    for (const fn of this._handlers.get(type) || []) fn({ target: this });
  }
}

function makeBundle() {
  const meetings = [
    { key: "m1", year: 2021, session: 22, date: "2021-05-25", url: "https://example.test/m1" },
    { key: "m2", year: 2021, session: 23, date: "2021-06-01", url: "https://example.test/m2" },
  ];
  const a = (o) => ({
    billNo: "1", category: "대통령령안", ministryId: "msit", ministry: "과학기술정보통신부",
    role: "정책안건", stc: "핵심", core: true, tags: [], why: "", cabinetResult: "", ...o,
  });
  return {
    meta: { range: ["2021-05-25", "2021-06-01"], meetings: 2, agendaTotal: 4, agendaStc: 3 },
    ministries: { msit: { name: "과학기술정보통신부", core: true }, molit: { name: "국토교통부", core: false } },
    meetings,
    reports: [],
    agenda: [
      // 여러 낱말 검색의 표적: "반도체"와 "특별법"이 제목 안에 떨어져 있다.
      a({ title: "반도체산업 경쟁력 강화 및 첨단전략산업 지원 특별법 일부개정법률안", meetingKey: "m1", date: "2021-05-25" }),
      a({ title: "도로교통법 시행령 일부개정령안", meetingKey: "m1", date: "2021-05-25",
          ministryId: "molit", ministry: "국토교통부", stc: null, core: false }),
      a({ title: "원전 안전관리에 관한 규정안", meetingKey: "m2", date: "2021-06-01" }),
      a({ title: "인공지능 기본계획안", meetingKey: "m2", date: "2021-06-01" }),
    ],
    utterances: [
      { speaker: "대통령", speakerType: "대통령", ministryId: null, stc: true, tags: [],
        text: "반도체 특별법을 조속히 처리해 주시기 바랍니다.", meetingKey: "m1", date: "2021-05-25" },
      { speaker: "국무총리", speakerType: "국무위원", ministryId: null, stc: true, tags: [],
        text: "원전 안전에 만전을 기해야 합니다.", meetingKey: "m2", date: "2021-06-01" },
    ],
  };
}

/** app.js를 스텁 DOM 위에서 구동하고, 조작용 손잡이를 돌려준다. */
async function boot() {
  const els = new Map();
  const getEl = (id) => {
    if (!els.has(id)) els.set(id, new El(id));
    return els.get(id);
  };
  // 초기 마크업이 주는 상태: 과기 필터 기본 ON.
  getEl("stcOnly").checked = true;

  const document = {
    getElementById: getEl,
    addEventListener() {},
    querySelector: () => null,
    createElement: () => ({ click() {}, remove() {} }),
    body: { appendChild() {} },
  };

  const bundle = makeBundle();
  const ctx = vm.createContext({
    document,
    fetch: async () => ({ ok: true, json: async () => bundle }),
    setTimeout, clearTimeout,
    console: { error() {} },
  });
  vm.runInContext(readFileSync(APP, "utf8"), ctx, { filename: "app.js" });

  // boot()의 await 체인이 끝나 데이터가 실릴 때까지 조건으로 기다린다.
  const deadline = Date.now() + 2000;
  while (!vm.runInContext("state.data", ctx)) {
    if (Date.now() > deadline) throw new Error("boot()이 끝나지 않았다");
    await new Promise((r) => setTimeout(r, 5));
  }

  return {
    ctx,
    el: getEl,
    /** 사용자가 검색창에 치는 것과 같은 경로 — 입력 이벤트 + 디바운스 대기. */
    async type(text) {
      getEl("q").value = text;
      getEl("q").dispatch("input");
      await new Promise((r) => setTimeout(r, 250)); // app.js 디바운스 180ms
    },
    /** 발언 패널·표의 "제N회 의결 안건 보기" 버튼이 부르는 그 함수. */
    drillTo(key) {
      vm.runInContext(`drillTo(${JSON.stringify(key)})`, ctx);
    },
    titles() {
      return vm.runInContext("state.filtered.map(a => a.title)", ctx);
    },
    utterancesHtml() {
      return getEl("utterances").hidden ? "" : getEl("utterances").innerHTML;
    },
  };
}

// ── 기준선 ──────────────────────────────────────────────────────────
test("검색어 한 낱말이면 안건과 발언을 함께 훑는다", async () => {
  const app = await boot();
  await app.type("원전");

  assert.deepEqual(app.titles(), ["원전 안전관리에 관한 규정안"]);
  assert.match(app.utterancesHtml(), /발언에서 <strong>1건<\/strong>/);
});

// ── 결함 A: 드릴다운 뒤 검색창이 먹통 ───────────────────────────────
test("회의 드릴다운 중에 새로 검색하면 드릴다운이 풀리고 검색이 먹는다", async () => {
  const app = await boot();
  await app.type("반도체");
  app.drillTo("m1"); // "제22회 의결 안건 보기" 클릭

  // 그 회의 안건 전부가 보여야 한다(과기 필터 무시) — 여기까진 의도된 동작.
  assert.deepEqual(app.titles().length, 2, "드릴다운은 그 회차 안건 전부를 보여준다");

  // 이제 사용자가 다른 말을 검색한다. 드릴다운에 갇히면 안 된다.
  await app.type("원전");

  assert.deepEqual(app.titles(), ["원전 안전관리에 관한 규정안"]);
  assert.equal(vm.runInContext("state.meetingFilter", app.ctx), null, "검색하면 드릴다운이 풀린다");
  assert.match(app.utterancesHtml(), /발언에서 <strong>1건<\/strong>/, "발언 패널도 다시 나온다");
});

test("드릴다운 중 검색어를 지우면 원래의 전체 목록으로 돌아온다", async () => {
  const app = await boot();
  app.drillTo("m1");
  await app.type("");

  assert.equal(vm.runInContext("state.meetingFilter", app.ctx), null);
  assert.equal(app.titles().length, 3, "과기 필터 ON 기준 전체 3건");
});

// ── 결함 B: 여러 낱말 검색이 통째 부분문자열로 취급됨 ───────────────
test("띄어쓴 검색어는 낱말을 모두 포함하는 안건을 찾는다", async () => {
  const app = await boot();
  await app.type("반도체 특별법");

  assert.deepEqual(app.titles(), [
    "반도체산업 경쟁력 강화 및 첨단전략산업 지원 특별법 일부개정법률안",
  ]);
});

test("띄어쓴 검색어는 발언 전문에도 똑같이 먹는다", async () => {
  const app = await boot();
  await app.type("특별법 반도체"); // 순서가 뒤집혀도 걸려야 한다

  assert.match(app.utterancesHtml(), /발언에서 <strong>1건<\/strong>/);
});

test("낱말 하나라도 없으면 걸리지 않는다", async () => {
  const app = await boot();
  await app.type("반도체 도로교통법");

  assert.deepEqual(app.titles(), []);
});
