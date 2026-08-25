import { describe, expect, it } from "vitest";

import { oauthReturnMessage, parseOAuthReturnSearch, stripOAuthReturnParams } from "../oauth/returnParams";

describe("oauth return params", () => {
  it("parses documented success and failure values", () => {
    expect(parseOAuthReturnSearch("?oauth=success&provider=gmail")).toEqual({
      oauth: "success",
      provider: "gmail",
      shouldRefresh: true,
    });
    expect(parseOAuthReturnSearch("oauth=identity_mismatch&provider=microsoft_graph")?.oauth).toBe(
      "identity_mismatch",
    );
  });

  it("treats unknown values as unknown without using them as copy", () => {
    const parsed = parseOAuthReturnSearch("?oauth=access_denied&provider=evil&error_description=boom");
    expect(parsed).toEqual({ oauth: "unknown", provider: null, shouldRefresh: true });
    expect(oauthReturnMessage(parsed!).text).toBe("Mailbox connection status is unavailable.");
    expect(oauthReturnMessage(parsed!).text).not.toContain("boom");
    expect(oauthReturnMessage(parsed!).text).not.toContain("access_denied");
  });

  it("strips only oauth return parameters", () => {
    expect(stripOAuthReturnParams("?oauth=success&provider=gmail&keep=1")).toBe("?keep=1");
    expect(stripOAuthReturnParams("?oauth=failed&provider=gmail")).toBe("");
  });

  it("ignores pages without oauth query values", () => {
    expect(parseOAuthReturnSearch("")).toBeNull();
    expect(parseOAuthReturnSearch("?other=1")).toBeNull();
  });
});
