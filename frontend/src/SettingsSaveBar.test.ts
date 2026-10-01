import { describe, expect, it } from "vitest";
import { settingsSaveState } from "./SettingsSaveBar";

describe("settings save state", () => {
  it("enables saving only for valid unsaved changes", () => {
    expect(settingsSaveState({ busy: false, monitoring: false, dirty: true, valid: true }))
      .toEqual({ message: "未保存の変更があります", tone: "unsaved", disabled: false });
  });

  it("explains why saving is unavailable", () => {
    expect(settingsSaveState({ busy: false, monitoring: false, dirty: false, valid: true }).message)
      .toBe("設定は保存済みです");
    expect(settingsSaveState({ busy: false, monitoring: false, dirty: true, valid: false }).message)
      .toContain("修正してください");
    expect(settingsSaveState({ busy: false, monitoring: true, dirty: true, valid: true }))
      .toEqual({ message: "警告設定は次回測定から反映されます", tone: "unsaved", disabled: false });
  });

  it("shows the validation error count", () => {
    expect(settingsSaveState({
      busy: false, monitoring: false, dirty: true, valid: false,
      validationMessage: "入力エラーが3件あります",
    }).message).toBe("入力エラーが3件あります");
  });
});
