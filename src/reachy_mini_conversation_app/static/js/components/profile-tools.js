/** Per-personality tool access controls. */

import {
  describeError,
  getProfileTools,
  resetProfileTools,
  saveProfileTools,
} from "../api.js";
import { h, prettifyProfileName, prettifyToolName } from "../ui.js";
import { confirmDialog } from "./confirm-dialog.js";

export function buildProfileToolsSection({ signal, initialProfile = null, onProfileChanged } = {}) {
  const profileSelect = h("select", {
    class: "settings-select",
    name: "profile_tools_profile",
    disabled: "disabled",
    "aria-label": "選擇要設定的人格",
  });
  const summary = h("div", { class: "settings-toolset-summary", "aria-live": "polite" });
  const toolGroups = h(
    "div",
    { class: "settings-tool-groups", "aria-live": "polite" },
    h("p", { class: "settings-hint" }, "正在載入工具權限…")
  );
  const status = h("p", { class: "settings-status", role: "status", "aria-live": "polite" });
  const resetButton = h(
    "button",
    { type: "button", class: "btn btn--ghost", disabled: "disabled" },
    "還原預設值"
  );
  const saveButton = h(
    "button",
    { type: "button", class: "btn btn--primary", disabled: "disabled" },
    "儲存工具權限"
  );
  const element = h(
    "section",
    { class: "settings-section" },
    h("h2", { class: "settings-section-title" }, "工具權限"),
    h(
      "p",
      { class: "settings-hint settings-section-intro" },
      "選擇各人格可使用的工具。已安裝的 Tool Spaces 須選取後才會啟用。"
    ),
    h(
      "label",
      { class: "settings-field" },
      h("span", { class: "settings-label" }, "設定對象"),
      profileSelect
    ),
    summary,
    toolGroups,
    h("div", { class: "settings-actions settings-toolset-actions" }, resetButton, saveButton),
    status
  );

  let currentPayload = null;
  let initialEnabledTools = new Set();
  let dirty = false;
  let busy = false;

  function selectedToolIds() {
    return Array.from(toolGroups.querySelectorAll('input[type="checkbox"]:checked')).map(
      (checkbox) => checkbox.value
    );
  }

  function selectionChanged() {
    const selectedTools = selectedToolIds();
    return (
      selectedTools.length !== initialEnabledTools.size ||
      selectedTools.some((toolId) => !initialEnabledTools.has(toolId))
    );
  }

  function syncActions() {
    const editable = currentPayload?.editable !== false;
    profileSelect.disabled = busy || !currentPayload?.profiles?.length;
    toolGroups.querySelectorAll('input[type="checkbox"]').forEach((checkbox) => {
      const disabled = busy || !editable;
      checkbox.disabled = disabled;
      checkbox.closest(".settings-tool-choice")?.classList.toggle("is-disabled", disabled);
    });
    resetButton.disabled = busy || !editable || !currentPayload?.overridden;
    saveButton.disabled = busy || !editable || !dirty;
  }

  function setBusy(nextBusy) {
    busy = nextBusy;
    element.toggleAttribute("aria-busy", nextBusy);
    syncActions();
  }

  function setDirty(nextDirty) {
    dirty = nextDirty;
    syncActions();
  }

  function populateProfiles(payload) {
    profileSelect.replaceChildren();
    for (const profile of payload.profiles || []) {
      const label = `${prettifyProfileName(profile.id)}${profile.active ? " · 使用中" : ""}`;
      profileSelect.appendChild(
        h("option", { value: profile.id, selected: profile.id === payload.profile ? "selected" : null }, label)
      );
    }
  }

  function renderSummary(payload) {
    const enabledCount = payload.enabled_tools?.length || 0;
    const pills = [];
    if (payload.is_active) pills.push(h("span", { class: "settings-pill is-active" }, "使用中"));
    if (payload.editable === false) pills.push(h("span", { class: "settings-pill" }, "已鎖定"));
    summary.replaceChildren(
      h(
        "div",
        { class: "settings-toolset-summary-copy" },
        h("strong", null, `已啟用 ${enabledCount} 個工具`),
        h(
          "span",
          { class: "settings-toolset-mode" },
          payload.overridden ? "已為此人格自訂" : "使用人格預設值"
        )
      ),
      ...pills
    );
  }

  function renderToolGroups(payload) {
    const enabled = new Set(payload.enabled_tools || []);
    const groups = new Map();
    for (const tool of payload.available_tools || []) {
      const key = tool.kind === "tool_space" ? `space:${tool.source}` : tool.kind;
      if (!groups.has(key)) {
        const sourceName = prettifyProfileName(tool.source.split("/").at(-1));
        let title = `Tool Space · ${sourceName}`;
        if (tool.kind === "shared") title = "內建工具";
        if (tool.kind === "external") title = "外部工具";
        groups.set(key, {
          title,
          tools: [],
        });
      }
      groups.get(key).tools.push(tool);
    }

    const unavailable = payload.unavailable_enabled_tools || [];
    if (unavailable.length) {
      groups.set("unavailable", {
        title: "無法使用的選項",
        tools: unavailable.map((toolId) => ({
          id: toolId,
          kind: "unavailable",
          source: "無法使用",
          description: "來源尚未安裝，或已不再提供此工具。",
        })),
      });
    }

    toolGroups.replaceChildren();
    if (!groups.size) {
      toolGroups.appendChild(h("p", { class: "settings-hint" }, "目前沒有可設定的工具。"));
      return;
    }

    for (const group of groups.values()) {
      const fieldset = h(
        "fieldset",
        { class: "settings-tool-group" },
        h(
          "legend",
          { class: "settings-tool-group-title" },
          group.title,
          h("span", { class: "settings-tool-group-count" }, String(group.tools.length))
        ),
        h(
          "div",
          { class: "settings-tool-grid" },
          ...group.tools.map((tool) => toolChoice(tool, enabled.has(tool.id)))
        )
      );
      fieldset.addEventListener("change", () => {
        const changed = selectionChanged();
        status.textContent = changed ? "有尚未儲存的變更" : "";
        status.classList.remove("is-error");
        setDirty(changed);
      });
      toolGroups.appendChild(fieldset);
    }
  }

  function render(payload) {
    currentPayload = payload;
    initialEnabledTools = new Set(payload.enabled_tools || []);
    populateProfiles(payload);
    renderSummary(payload);
    renderToolGroups(payload);
    status.classList.remove("is-error");
    status.textContent = payload.editable === false ? "管理員已鎖定工具編輯。" : "";
    setDirty(false);
  }

  async function load(profile = null) {
    setBusy(true);
    status.classList.remove("is-error");
    status.textContent = "正在載入工具…";
    try {
      const payload = await getProfileTools(profile);
      if (signal?.aborted) return;
      render(payload);
      onProfileChanged?.(payload.profile);
    } catch (error) {
      if (signal?.aborted) return;
      status.textContent = `無法載入工具權限：${describeError(error)}`;
      status.classList.add("is-error");
      if (currentPayload) {
        profileSelect.value = currentPayload.profile;
      } else {
        toolGroups.replaceChildren();
      }
    } finally {
      if (!signal?.aborted) setBusy(false);
    }
  }

  async function confirmDiscard() {
    if (!dirty) return true;
    return confirmDialog({
      title: "捨棄尚未儲存的工具變更？",
      message: "此人格的工具選擇尚未儲存。",
      confirmLabel: "捨棄變更",
      signal,
    });
  }

  profileSelect.addEventListener("change", async () => {
    const selectedProfile = profileSelect.value;
    if (!(await confirmDiscard())) {
      profileSelect.value = currentPayload?.profile || "";
      return;
    }
    await load(selectedProfile);
  });

  saveButton.addEventListener("click", async () => {
    if (saveButton.disabled || !currentPayload) return;
    const enabledTools = selectedToolIds();
    setBusy(true);
    status.classList.remove("is-error");
    status.textContent = "正在儲存工具權限…";
    try {
      const payload = await saveProfileTools(currentPayload.profile, enabledTools);
      if (signal?.aborted) return;
      render(payload);
      status.textContent = payload?.message || "工具權限已儲存。";
    } catch (error) {
      if (signal?.aborted) return;
      status.textContent = `無法儲存工具權限：${describeError(error)}`;
      status.classList.add("is-error");
    } finally {
      if (!signal?.aborted) setBusy(false);
    }
  });

  resetButton.addEventListener("click", async () => {
    if (resetButton.disabled || !currentPayload) return;
    const confirmed = await confirmDialog({
      title: "還原人格預設值？",
      message: `這會取代「${prettifyProfileName(currentPayload.profile)}」的自訂工具選擇。`,
      confirmLabel: "還原預設值",
      signal,
    });
    if (!confirmed || signal?.aborted) return;

    setBusy(true);
    status.classList.remove("is-error");
    status.textContent = "正在還原預設值…";
    try {
      const payload = await resetProfileTools(currentPayload.profile);
      if (signal?.aborted) return;
      render(payload);
      status.textContent = payload?.message || "已還原人格預設值。";
    } catch (error) {
      if (signal?.aborted) return;
      status.textContent = `無法還原預設值：${describeError(error)}`;
      status.classList.add("is-error");
    } finally {
      if (!signal?.aborted) setBusy(false);
    }
  });

  return {
    element,
    confirmDiscard,
    hasUnsavedChanges() {
      return dirty;
    },
    async refresh() {
      await load(currentPayload?.profile || initialProfile);
    },
  };
}

const BUILT_IN_TOOL_LABELS = Object.freeze({
  camera: ["拍照查看", "依請求拍攝當下畫面，描述機器人前方的內容。"],
  dance: ["跳舞", "播放指定或隨機舞步一次，或重複播放；不阻塞對話。"],
  forget: ["忘記記憶", "依使用者要求刪除已儲存的長期記憶。"],
  go_to_sleep: ["睡眠並結束", "使用者明確要求時，讓 Reachy 睡眠並結束目前應用程式。"],
  head_tracking: ["臉部追蹤", "啟用或停用頭部跟隨使用者臉部的功能。"],
  idle_do_nothing: ["待機保持安靜", "在待機更新時選擇保持不動與安靜。"],
  move_head: ["轉動頭部", "將頭部轉向左、右、上、下或正前方。"],
  play_emotion: ["表達情緒", "播放符合所需情緒的機器人動作。"],
  remember: ["儲存記憶", "儲存一筆使用者明確分享的穩定資訊，供未來對話使用。"],
  robot_status: ["機器人狀態", "查詢名稱、軟體、網路、帳號、感測器或應用程式狀態。"],
  stop_dance: ["停止跳舞", "停止目前的舞蹈動作。"],
  stop_emotion: ["停止情緒動作", "停止目前的情緒動作。"],
  sweep_look: ["環顧四周", "轉動頭部與身體向左右查看，再回到中央。"],
  task_cancel: ["取消背景任務", "確認後取消正在執行的背景工具任務。"],
  task_status: ["背景任務狀態", "查詢背景工具任務的執行狀態。"],
  volume_control: ["音量控制", "讀取或設定喇叭、麥克風音量；設定喇叭時會播放確認音。"],
});

function toolChoice(tool, checked) {
  const unavailable = tool.kind === "unavailable";
  const display = tool.kind === "shared" ? BUILT_IN_TOOL_LABELS[tool.id] : null;
  const input = h("input", {
    type: "checkbox",
    value: tool.id,
    checked: checked ? "checked" : null,
  });
  return h(
    "label",
    {
      class: ["settings-tool-choice", unavailable && "is-unavailable"],
    },
    input,
    h(
      "span",
      { class: "settings-tool-choice-copy" },
      h("strong", { class: "settings-tool-choice-name" }, display?.[0] || prettifyToolName(tool.id)),
      tool.kind === "unavailable" ? h("code", { class: "settings-tool-choice-id" }, tool.id) : null,
      tool.description ? h("span", { class: "settings-tool-choice-description" }, display?.[1] || tool.description) : null
    )
  );
}
