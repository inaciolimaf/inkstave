import { describe, expect, it } from "vitest";

import i18n from "@/i18n/config";

import { allowConsole } from "./console-guard";

describe("console guard", () => {
  it("turns a missing i18n key into console output", () => {
    // The guard fails any test that writes this message unless the test allows it, so allow it here and
    // assert on the call instead: the handler reaches console.warn, which the guard records.
    allowConsole(/missing i18n key: common:guard\.absent/);
    i18n.t("guard.absent", { ns: "common" });
    expect(console.warn).toHaveBeenCalledWith("missing i18n key: common:guard.absent");
  });

  it("lets a test expect a message it allows", () => {
    allowConsole(/expected on purpose/);
    console.error("expected on purpose");
  });
});
