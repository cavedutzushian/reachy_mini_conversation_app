import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { parseArgs } from "node:util";
import vm from "node:vm";

const { values } = parseArgs({ options: {
  chrome: { type: "string" }, puppeteer: { type: "string" },
  url: { type: "string", default: "http://127.0.0.1:7864" },
  phase: { type: "string", default: "all" },
} });
assert(values.chrome && values.puppeteer, "Specify --chrome and --puppeteer paths");
const origin = new URL(values.url).origin;
assert(["127.0.0.1", "localhost", "[::1]"].includes(new URL(origin).hostname));
const { default: puppeteer } = await import(pathToFileURL(resolve(values.puppeteer)).href);
const browser = await puppeteer.launch({ executablePath: values.chrome, headless: true, args: ["--disable-background-networking"] });
const errors = [];
let websocketLeak = false;
const responses = [];
const unreadResponses = [];
let echoed = false;
const sentinels = ["offline-first", "offline-second", "offline-invalid"];
const localHost = origin.replace("127.0.0.1", "localhost");
let completed = 0;

async function scenario(scene = "none", options = {}) {
  const response = await fetch(origin + "/fixture/control", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scene, ...options }) });
  assert.equal(response.status, 200);
  assert.equal((await response.json()).fake_only,true,"Target must be the offline fixture");
}
async function newPage() {
  const page = await browser.newPage();
  page.setDefaultTimeout(7000);
  page.setDefaultNavigationTimeout(20000);
  const session=await page.createCDPSession();
  await session.send("Network.enable");
  session.on("Network.webSocketFrameSent", event=>{
    if(sentinels.some(value=>event.response.payloadData.includes(value))) websocketLeak=true;
  });
  page.on("pageerror", error => errors.push(error.message));
  await page.setRequestInterception(true);
  page.on("request", request => {
    const address = new URL(request.url());
    if (address.origin !== origin && address.origin !== localHost) return request.abort();
    request.continue();
  });
  page.on("response", response => {
    if (response.url().includes("/api/gemini-credential")) {
      responses.push(response.text().then(text => { if (sentinels.some(value => text.includes(value))) echoed = true; }, () => unreadResponses.push(response.request().method())));
    }
  });
  return page;
}
async function waitReady(page) {
  await page.waitForSelector("#credential-apply:not([disabled])");
  assert.equal(await page.$eval("#credential-input", node => node.value), "");
  assert.equal(await page.$eval("#credential-input", node => node.type), "password");
}
async function apply(page, key, expected) {
  await page.type("#credential-input", key);
  await page.click("#credential-apply");
  await page.waitForFunction(text => document.querySelector("#credential-result")?.textContent.includes(text), {}, expected);
  assert.equal(await page.$eval("#credential-input", node => node.value), "");
}
async function clear(page, expected = "已移除") {
  await page.click("#credential-clear");
  await page.waitForSelector('[role="dialog"]');
  await page.click(".modal__actions .btn--danger");
  await page.waitForFunction(text => document.querySelector("#credential-result")?.textContent.includes(text), {}, expected);
}

try {
  if (["all", "eligibility"].includes(values.phase)) {
    const source = await readFile(new URL("../../../src/reachy_mini_conversation_app/static/js/gemini-key.js", import.meta.url), "utf8");
    for (const mode of ["missing", "empty", "throws", "null", "unknown", "http", "path", "port", "native", "native-grandparent", "remote", "suffix", "scheme", "dev", "https-parent", "empty-item", "mixed-null", "trusted-self"]) {
      const location = { protocol: "http:", hostname: "127.0.0.1", pathname: "/", origin };
      const window = { top: {}, location };
      if (mode === "throws") Object.defineProperty(location, "ancestorOrigins", { get() { throw new Error("unavailable"); } });
      else if (mode !== "missing") location.ancestorOrigins = mode === "empty" ? [] : [mode === "null" ? "null" : "http://tauri.localhost:1420"];
      if (mode === "native") location.ancestorOrigins = ["http://tauri.localhost"];
      if (mode === "native-grandparent") location.ancestorOrigins = ["http://tauri.localhost", "http://localhost:1420"];
      if (mode === "remote") { location.hostname = "192.0.2.1"; window.top = window; }
      if (mode === "suffix") location.ancestorOrigins = ["http://tauri.localhost.attacker.test"];
      if (mode === "scheme") location.ancestorOrigins = ["tauri://localhost"];
      if (mode === "dev") location.ancestorOrigins = ["http://localhost:1420"];
      if (mode === "https-parent") location.ancestorOrigins = ["https://tauri.localhost"];
      if (mode === "empty-item") location.ancestorOrigins = [""];
      if (mode === "mixed-null") location.ancestorOrigins = [origin, "null"];
      if (mode === "trusted-self") location.ancestorOrigins = [origin, "http://tauri.localhost"];
      if (mode === "http") { location.protocol = "https:"; window.top = window; }
      if (mode === "path") { location.pathname = "/relay"; window.top = window; }
      const context = vm.createContext({ window, location, URL });
      const module = new vm.SourceTextModule(source, { context });
      await module.link(async () => {
        const exports = ["geminiCredentialRequest", "retryBackend", "confirmDialog", "h"];
        return new vm.SyntheticModule(exports, function () {
          for (const name of exports) this.setExport(name, () => { throw new Error("Import must have no side effects"); });
        }, { context });
      });
      await module.evaluate();
      assert.equal(module.namespace.canManageGeminiCredential(), (mode === "native" || mode === "trusted-self"), mode);
      completed++;
    }
    for (const [label, url, expected] of [
      ["top", origin + "/#/settings", true],
      ["trusted", origin + "/fixture/wrapper", true],
      ["hostile", localHost + "/fixture/wrapper", false],
      ["grandparent", localHost + "/fixture/grandparent", false],
    ]) {
      console.log("eligibility: " + label);
      await scenario();
      const page = await newPage();
      await page.goto(url, {waitUntil:"domcontentloaded"});
      const frame = await page.waitForFrame(frame => frame.url() === origin + "/#/settings");
      const result = await frame.evaluate(async () => (await import("/static/js/gemini-key.js")).canManageGeminiCredential());
      assert.equal(result, expected, label);
      await page.close();
      completed++;
    }
  }
  if (["all", "initial"].includes(values.phase)) {
    await scenario();
    const page = await newPage();
    await page.goto(origin + "/#/settings", {waitUntil:"domcontentloaded"});
    await waitReady(page);
    await page.type("#credential-input", "draft");
    await page.click("#credential-cancel");
    assert.equal(await page.$eval("#credential-input", node => node.value), "");
    await page.type("#credential-input","offline-first");
    await page.evaluate(()=>[...document.querySelectorAll("button")].find(node=>node.textContent==="儲存連線").click());
    await page.waitForFunction(()=>[...document.querySelectorAll("form")].filter(node=>node.id!=="credential-form").every(node=>!node.hasAttribute("aria-busy")));
    assert.equal((await (await fetch(origin+"/fixture/status")).json()).requests.filter(method=>method==="POST").length,0);
    await page.click("#credential-cancel");
    await page.reload();
    await waitReady(page);
    await apply(page, "offline-first", "已驗證並套用");
    assert.equal((await browser.pages()).length, 2, "Must not open another page");
    await page.reload();
    await waitReady(page);
    await scenario("restart");
    await page.reload();
    await waitReady(page);
    assert((await page.$eval("#credential-state", node => node.textContent)).includes("設定頁"));
    await page.close();
    completed++;
  }
  if (["all", "lifecycle"].includes(values.phase)) {
    await scenario("both");
    const page = await newPage();
    await page.goto(origin + "/#/settings", {waitUntil:"domcontentloaded"});
    await waitReady(page);
    await apply(page, "offline-second", "已驗證並套用");
    await apply(page, "offline-invalid", "認證失敗");
    assert.equal((await (await fetch(origin + "/fixture/status")).json()).entries, 1);
    await page.click("#credential-clear");
    await page.waitForSelector('[role="dialog"]');
    await page.keyboard.press("Escape");
    assert.equal(await page.$('[role="dialog"]'), null);
    await clear(page);
    assert((await page.$eval("#credential-state", node=>node.textContent)).includes("既有環境"));
    await page.type("#credential-input", "draft");
    await page.evaluate(()=>window.dispatchEvent(new PageTransitionEvent("pagehide", {persisted:true})));
    assert.equal(await page.$("#credential-input"),null);
    await page.evaluate(()=>window.dispatchEvent(new PageTransitionEvent("pageshow", {persisted:true})));
    await waitReady(page);
    await page.type("#credential-input", "draft");
    await page.goto("about:blank", {waitUntil:"domcontentloaded"});
    await page.goBack({waitUntil:"domcontentloaded"});
    await waitReady(page);
    await page.close();
    completed++;

    await scenario("none", {delay:2});
    const race = await newPage();
    await race.goto(origin + "/#/settings", {waitUntil:"domcontentloaded"});
    await waitReady(race);
    await race.type("#credential-input", "offline-first");
    await race.click("#credential-apply");
    await clear(race);
    await new Promise(resolve=>setTimeout(resolve,2100));
    const status=await (await fetch(origin + "/fixture/status")).json();
    assert.equal(status.source,"none");
    assert.equal(status.entries,0);
    assert.equal(status.requests.filter(method=>method==="POST").length,1);
    assert.equal(status.requests.filter(method=>method==="DELETE").length,1);
    await race.close();
    completed++;

    await scenario("none", {delay:1});
    const late = await newPage();
    await late.goto(origin + "/#/settings", {waitUntil:"domcontentloaded"});
    await waitReady(late);
    await late.type("#credential-input", "offline-second");
    await late.click("#credential-apply");
    await late.evaluate(()=>{location.hash="#/";});
    await late.waitForFunction(()=>!document.querySelector("#credential-input"));
    await late.evaluate(()=>{location.hash="#/settings";});
    await waitReady(late);
    await new Promise(resolve=>setTimeout(resolve,1300));
    const lateStatus=await (await fetch(origin + "/fixture/status")).json();
    assert.equal(lateStatus.requests.filter(method=>method==="POST").length,1);
    assert.equal(await late.$eval("#credential-input",node=>node.value),"");
    await late.close();
    completed++;
  }
  if (["all", "stale-read"].includes(values.phase)) {
    await scenario();
    const page=await newPage();
    await page.goto(origin + "/#/settings", {waitUntil:"domcontentloaded"});
    await waitReady(page);
    await page.evaluate(()=>{
      const originalFetch=window.fetch.bind(window);
      let hold=true;
      window.fetch=(url,options)=>{
        if(hold && String(url).includes("/api/gemini-credential") && options?.method==="GET") {
          hold=false;
          return new Promise((resolve,reject)=>{window.rejectHeldGet=()=>reject(new TypeError("Simulated old read failure"));});
        }
        return originalFetch(url,options);
      };
    });
    await page.click("#credential-refresh");
    await page.waitForFunction(()=>typeof window.rejectHeldGet==="function");
    await apply(page,"offline-first","已驗證並套用");
    await page.evaluate(()=>window.rejectHeldGet());
    await new Promise(resolve=>setTimeout(resolve,100));
    assert.notEqual(await page.$("#credential-input"),null,"Old read error must not retire newer successful controls");
    await page.close();
    completed++;
  }
  if (["all", "security"].includes(values.phase)) {
    for (const source of ["none", "environment", "managed", "both"]) {
      await scenario(source);
      const page = await newPage();
      await page.goto(origin + "/#/settings", {waitUntil:"domcontentloaded"});
      await waitReady(page);
      const initial=await (await fetch(origin + "/fixture/status")).json();
      assert.equal(initial.source, source === "managed" || source === "both" ? "settings" : source);
      await apply(page,"offline-second","已驗證並套用");
      await scenario("restart");
      await page.reload();
      await waitReady(page);
      assert((await page.$eval("#credential-state",node=>node.textContent)).includes("設定頁"));
      await clear(page);
      const cleared=await (await fetch(origin + "/fixture/status")).json();
      assert.equal(cleared.source,source === "environment" || source === "both" ? "environment" : "none");
      const storage=await page.evaluate(()=>JSON.stringify({local:{...localStorage},session:{...sessionStorage}}));
      assert(sentinels.every(value=>!storage.includes(value)));
      assert(sentinels.every(value=>!page.url().includes(value)));
      await page.close();
      completed++;
    }
    for (const [provider,connection] of [["huggingface","connected"],["gemini","connected"],["gemini","disconnected"]]) {
      await scenario("both",{provider,connection});
      const page=await newPage();
      await page.goto(origin + "/#/settings", {waitUntil:"domcontentloaded"});
      await waitReady(page);
      await apply(page,"offline-second","已驗證並套用");
      await apply(page,"offline-invalid","認證失敗");
      const failed=await (await fetch(origin + "/fixture/status")).json();
      assert.equal(failed.backend,provider);
      assert.equal(failed.source,"settings");
      assert.equal(failed.entries,1);
      if(provider === "gemini") assert.equal(failed.manual_reconnect_required,true);
      await clear(page);
      const cleared=await (await fetch(origin + "/fixture/status")).json();
      assert.equal(cleared.manual_reconnect_required,true);
      await page.close();
      completed++;
    }
    for (const name of ["wrapper","grandparent","hidden-parent","opaque"]) {
      await scenario();
      const page=await newPage();
      await page.goto(localHost + "/fixture/" + name, {waitUntil:"domcontentloaded"});
      const frame=await page.waitForFrame(frame=>frame.url() === origin + "/#/settings");
      if(name !== "opaque") await frame.waitForSelector(".credential-controls");
      assert.equal(await frame.$("#credential-input"),null);
      const status=await (await fetch(origin + "/fixture/status")).json();
      assert.equal(status.requests.length,0,"Untrusted frame must not bootstrap");
      await page.close();
      completed++;
    }
    await scenario("none",{bootstrap_delay:1});
    const pending=await newPage();
    await pending.goto(origin + "/#/settings", {waitUntil:"domcontentloaded"});
    await pending.waitForSelector(".credential-controls");
    assert.equal(await pending.$("#credential-input"),null);
    await pending.evaluate(()=>{location.hash="#/";});
    await pending.waitForFunction(()=>!document.querySelector(".credential-controls"));
    await pending.evaluate(()=>{location.hash="#/settings";});
    await waitReady(pending);
    assert.equal(await pending.$eval("#credential-input",node=>node.value),"");
    await pending.close();
    completed++;

    await scenario("none",{bootstrap_failure:true});
    const unavailable=await newPage();
    await unavailable.goto(origin + "/#/settings", {waitUntil:"domcontentloaded"});
    await unavailable.waitForFunction(()=>document.querySelector(".credential-controls")?.textContent.includes("重新查詢"));
    assert.equal(await unavailable.$("#credential-input"),null);
    await unavailable.close();
    completed++;

    for(const failure of ["set","delete"]) {
      await scenario("both",{failure});
      const page=await newPage();
      await page.goto(origin + "/#/settings", {waitUntil:"domcontentloaded"});
      await waitReady(page);
      if(failure === "set") await apply(page,"offline-second","未完成");
      else await clear(page,"清除未完成");
      const status=await (await fetch(origin + "/fixture/status")).json();
      assert.notEqual(status.source,"environment");
      assert.equal(status.entries,1);
      await page.close();
      completed++;
    }
  }
  if (["all", "security", "layout"].includes(values.phase)) {
    await scenario();
    const narrow=await newPage();
    await narrow.setViewport({width:360,height:820});
    await narrow.goto(origin + "/#/settings", {waitUntil:"domcontentloaded"});
    await waitReady(narrow);
    assert.equal(await narrow.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,"Narrow settings overflow");
    await narrow.type("#credential-input","draft");
    await narrow.keyboard.press("Escape");
    assert.equal(await narrow.$eval("#credential-input",node=>node.value),"");
    for (const width of [240, 280, 320, 360, 768, 1280]) {
      await narrow.setViewport({width, height:820});
      const outside = await narrow.$$eval(".credential-controls, .credential-controls *", nodes => nodes.filter(node => {
        const frame = node.closest(".settings-section");
        const bounds = node.getBoundingClientRect();
        const container = frame.getBoundingClientRect();
        return bounds.left < container.left || bounds.right > container.right;
      }).map(node => node.id || node.className || node.tagName));
      assert.deepEqual(outside, [], `Credential elements outside connection section at ${width}px`);
      const textOutside = await narrow.$eval(".credential-controls", outlet => {
        const container = outlet.closest(".settings-section").getBoundingClientRect();
        const walker = document.createTreeWalker(outlet, NodeFilter.SHOW_TEXT);
        const outside = [];
        while (walker.nextNode()) {
          const range = document.createRange();
          range.selectNodeContents(walker.currentNode);
          if ([...range.getClientRects()].some(bounds => bounds.left < container.left || bounds.right > container.right)) {
            outside.push(walker.currentNode.parentElement.id || walker.currentNode.parentElement.tagName);
          }
        }
        return outside;
      });
      assert.deepEqual(textOutside, [], `Credential text outside connection section at ${width}px`);
      assert.equal(await narrow.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `Overflow at ${width}px`);
    }
    await narrow.setViewport({width:280, height:820});
    await narrow.screenshot({path:resolve("cache/inline-settings-narrow.png"),fullPage:true});
    await narrow.close();
    completed++;
  }
  if (["all", "timeout"].includes(values.phase)) {
    await scenario();
    const page = await newPage();
    await page.evaluateOnNewDocument(() => {
      const originalFetch = window.fetch.bind(window);
      window.allowCredentialReads = false;
      window.fetch = (url, options) => {
        if (!window.allowCredentialReads && String(url).includes("/api/gemini-credential") && options?.method === "GET") {
          return new Promise((resolve, reject) => {
            if (options.signal?.aborted) reject(new DOMException("Aborted", "AbortError"));
            else options.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), {once:true});
          });
        }
        return originalFetch(url, options);
      };
    });
    await page.goto(origin + "/#/settings", {waitUntil:"domcontentloaded"});
    await page.waitForFunction(() => document.querySelector(".credential-controls")?.textContent.includes("重新查詢金鑰狀態"), {timeout:13000});
    assert.equal(await page.$("#credential-input"), null, "Hung bootstrap must not enable secret input");
    assert.equal((await (await fetch(origin + "/fixture/status")).json()).requests.length, 0);
    await page.evaluate(() => { window.allowCredentialReads = true; });
    await page.click(".credential-controls button");
    await waitReady(page);
    assert.deepEqual((await (await fetch(origin + "/fixture/status")).json()).requests, ["GET"]);
    await page.close();
    completed++;
  }
  await Promise.all(responses);
  assert.equal(echoed, false, "Credential echoed in response");
  assert.equal(websocketLeak,false,"Credential submitted through ordinary RPC");
  assert(unreadResponses.every(method => method === "GET"), "Mutation response unavailable");
  assert.deepEqual(errors, []);
  console.log(`PASS: ${completed} browser cases (${values.phase})`);
} finally {
  await browser.close();
}
