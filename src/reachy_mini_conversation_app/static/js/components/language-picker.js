/**
 * Flag pill next to the personality badge: picks the conversation language and
 * saves it for the active personality only or for all of them.
 */

import { describeError, getLanguage, setLanguage } from "../api.js";
import { h, prettifyProfileName } from "../ui.js";

const AUTO_CHOICE = Object.freeze({ code: "auto", name: "自動判斷", native_name: "自動判斷", flag: "🌐" });

const VIEWPORT_GUTTER_PX = 16;

const CHEVRON_SVG =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>';

/**
 * Fill `root` with the picker; it stays hidden until `refresh()` first succeeds.
 *
 * @param {{ root: HTMLElement, signal: AbortSignal, onStatus?: (message: string) => void }} options
 */
export function createLanguagePicker({ root, signal, onStatus }) {
  let state = null; // last language.get / language.set result
  let scope = "all";
  let busy = false;

  const flagEl = h("span", { class: "language-picker__flag", "aria-hidden": "true" });
  const nameEl = h("span", { class: "language-picker__name" });
  const trigger = h(
    "button",
    {
      type: "button",
      class: "language-picker__trigger",
      "aria-haspopup": "dialog",
      "aria-expanded": "false",
      onClick: () => setOpen(menu.hidden),
    },
    flagEl,
    nameEl,
    h("span", { class: "language-picker__chevron", "aria-hidden": "true", html: CHEVRON_SVG })
  );

  const scopeInputs = {
    profile: h("input", { type: "radio", name: "language-scope", value: "profile" }),
    all: h("input", { type: "radio", name: "language-scope", value: "all" }),
  };
  for (const input of Object.values(scopeInputs)) {
    input.addEventListener("change", () => {
      scope = input.value;
    });
  }
  const scopeFieldset = h(
    "fieldset",
    { class: "language-picker__scope" },
    h("legend", {}, "儲存範圍"),
    h(
      "div",
      { class: "language-picker__scope-options" },
      h("label", { class: "language-picker__scope-option" }, scopeInputs.profile, h("span", {}, "此人格")),
      h("label", { class: "language-picker__scope-option" }, scopeInputs.all, h("span", {}, "所有人格"))
    )
  );
  const optionsEl = h("div", { class: "language-picker__options", role: "group", "aria-label": "語言" });
  const menu = h(
    "div",
    { class: "language-picker__menu", role: "dialog", "aria-label": "對話語言", hidden: true },
    scopeFieldset,
    optionsEl
  );

  root.replaceChildren(trigger, menu);
  document.addEventListener("pointerdown", onDocumentPointerDown, { signal });
  document.addEventListener("keydown", onDocumentKeyDown, { signal });
  signal.addEventListener(
    "abort",
    () => {
      root.hidden = true;
      root.replaceChildren();
    },
    { once: true }
  );

  async function refresh() {
    try {
      state = await getLanguage();
    } catch (error) {
      console.warn("Failed to load the conversation language", error);
      return;
    }
    if (signal.aborted) return;
    render();
    root.hidden = false;
  }

  function savedScope() {
    return state.profile_language ? "profile" : "all";
  }

  function choiceFor(code) {
    if (code === AUTO_CHOICE.code) return AUTO_CHOICE;
    const choice = state.choices.find((candidate) => candidate.code === code);
    if (choice?.code === "zh") return { ...choice, name: "中文（繁體優先）", native_name: "中文（繁體優先）" };
    return choice || { code, name: code.toUpperCase(), native_name: code.toUpperCase(), flag: "" };
  }

  function render() {
    const current = choiceFor(state.language);
    const profileName = prettifyProfileName(state.profile);
    flagEl.textContent = current.flag;
    nameEl.textContent = current.native_name;
    trigger.setAttribute(
      "aria-label",
      `對話語言：${current.name}，儲存對象：${state.profile_language ? profileName : "所有人格"}`
    );
    trigger.title = state.profile_language ? `僅為 ${profileName} 儲存` : "已儲存供所有人格使用";

    scope = savedScope();
    scopeInputs.profile.parentElement.title = `僅限 ${profileName}`;
    scopeInputs.profile.checked = scope === "profile";
    scopeInputs.all.checked = scope === "all";

    optionsEl.replaceChildren(
      ...[AUTO_CHOICE, ...state.choices.map((choice) => choiceFor(choice.code))].map((choice) =>
        h(
          "button",
          {
            type: "button",
            class: ["language-picker__option", choice === AUTO_CHOICE && "language-picker__option--auto"],
            "aria-pressed": String(choice.code === current.code),
            title: choice.name,
            onClick: () => choose(choice.code),
          },
          h("span", { class: "language-picker__flag", "aria-hidden": "true" }, choice.flag),
          h("span", { lang: choice === AUTO_CHOICE ? null : choice.code }, choice.native_name)
        )
      )
    );
  }

  async function choose(code) {
    if (busy) return;
    if (code === state.language && scope === savedScope()) {
      setOpen(false);
      return;
    }
    busy = true;
    for (const option of optionsEl.children) option.disabled = true;
    try {
      state = await setLanguage(code, scope);
      if (signal.aborted) return;
      setOpen(false);
      onStatus?.(state.message);
    } catch (error) {
      if (!signal.aborted) onStatus?.(`無法變更語言：${describeError(error)}`);
    } finally {
      busy = false;
      if (!signal.aborted) render();
    }
  }

  function setOpen(open) {
    menu.hidden = !open;
    trigger.setAttribute("aria-expanded", String(open));
    if (!open) return;
    // The pill can sit anywhere in the wrapping personality row; keep the menu on screen.
    menu.style.left = "0px";
    const overflow = menu.getBoundingClientRect().right - (window.innerWidth - VIEWPORT_GUTTER_PX);
    if (overflow > 0) menu.style.left = `${-overflow}px`;
    optionsEl.querySelector('[aria-pressed="true"]')?.focus();
  }

  function onDocumentPointerDown(event) {
    if (!menu.hidden && !root.contains(event.target)) setOpen(false);
  }

  function onDocumentKeyDown(event) {
    if (event.key !== "Escape" || menu.hidden) return;
    setOpen(false);
    trigger.focus();
  }

  return { refresh };
}
