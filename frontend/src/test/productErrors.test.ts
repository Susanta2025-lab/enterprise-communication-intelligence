import { describe, expect, it } from "vitest";

import { EciApiError } from "../api/errors";
import {
  BACK_TO_DASHBOARD_LABEL,
  REFRESH_MAILBOX_LABEL,
  REFRESH_STATUS_LABEL,
  SIGN_IN_LABEL,
  TEST_PRIVACY_NOTICE_COPY,
  TEST_PRIVACY_NOTICE_TITLE,
  TRY_AGAIN_LABEL,
} from "../errors/copy";
import { presentProductError } from "../errors/presentProductError";

function apiError(status: number, message = "raw provider boom"): EciApiError {
  return new EciApiError(status, "http_error", message);
}

describe("presentProductError", () => {
  it("maps 401 to a session-unusable state with Sign in and no retry", () => {
    for (const operation of [
      "connector_list",
      "connector_lifecycle",
      "mailbox_list",
      "analyze",
      "propose",
      "review",
      "execute",
      "workflow_refresh",
      "api_smoke",
    ] as const) {
      const view = presentProductError(operation, apiError(401, "invalid_token"));
      expect(view.message).toContain("session is no longer usable");
      expect(view.message).toContain("Sign in again");
      expect(view.showSignIn).toBe(true);
      expect(view.retryLabel).toBeNull();
      expect(view.message).not.toContain("invalid_token");
    }
  });

  it("keeps connector, mailbox, analyze, and execute 409 copy distinct", () => {
    const connector = presentProductError("connector_list", apiError(409));
    const mailbox = presentProductError("mailbox_list", apiError(409));
    const analyze = presentProductError("analyze", apiError(409));
    const review = presentProductError("review", apiError(409));
    const execute = presentProductError("execute", apiError(409));

    expect(connector.message).toContain("Mailbox connections cannot be updated");
    expect(mailbox.message).toBe("This mailbox is not available right now.");
    expect(analyze.message).toBe("This mailbox is not available right now.");
    expect(review.message).toBe("This workflow action changed. Refresh its status.");
    expect(review.retryLabel).toBe(REFRESH_STATUS_LABEL);
    expect(execute.message).toContain("cannot be sent right now");
    expect(execute.retryLabel).toBe(REFRESH_STATUS_LABEL);
    expect(execute.showDashboardLink).toBe(true);
  });

  it("does not treat mailbox or execute 503 as reauthorization", () => {
    const mailbox = presentProductError("mailbox_list", apiError(503, "provider timeout"));
    const analyze = presentProductError("analyze", apiError(503, "foundry timeout"));
    const execute = presentProductError("execute", apiError(503, "smtp stack"));

    expect(mailbox.message).toBe("Mailbox is temporarily unavailable.");
    expect(mailbox.retryLabel).toBe(TRY_AGAIN_LABEL);
    expect(analyze.message).toBe("Analysis could not be completed.");
    expect(analyze.retryLabel).toBe(TRY_AGAIN_LABEL);
    expect(execute.message).toBe("Sending status is uncertain. Do not send again.");
    expect(execute.retryLabel).toBe(REFRESH_STATUS_LABEL);
    expect(execute.retryLabel).not.toBe(TRY_AGAIN_LABEL);
    expect(mailbox.message).not.toMatch(/reauth|reconnect required/i);
    expect(analyze.message).not.toMatch(/reauth|reconnect required/i);
    expect(execute.message).not.toContain("smtp stack");
  });

  it("maps permission 403 copy to the operation", () => {
    expect(presentProductError("mailbox_list", apiError(403)).message).toContain("communications:read");
    expect(presentProductError("analyze", apiError(403)).message).toContain("analyze");
    expect(presentProductError("propose", apiError(403)).message).toContain("communications:workflow");
    expect(presentProductError("execute", apiError(403)).message).toContain("communications:send");
    expect(presentProductError("mailbox_list", apiError(403)).retryLabel).toBeNull();
    expect(presentProductError("execute", apiError(403)).retryLabel).toBeNull();
  });

  it("recovers an invalid mailbox cursor with Refresh mailbox", () => {
    const view = presentProductError("mailbox_list", apiError(400, "opaque/cursor"));
    expect(view.message).toContain("no longer valid");
    expect(view.retryLabel).toBe(REFRESH_MAILBOX_LABEL);
    expect(view.message).not.toContain("opaque/cursor");
  });

  it("never offers Try again for execute failures", () => {
    for (const status of [400, 403, 404, 409, 500, 503]) {
      const view = presentProductError("execute", apiError(status));
      expect(view.retryLabel).not.toBe(TRY_AGAIN_LABEL);
      expect(view.retryLabel ?? "").not.toMatch(/retry send/i);
    }
  });

  it("uses stable action labels", () => {
    expect(SIGN_IN_LABEL).toBe("Sign in");
    expect(TRY_AGAIN_LABEL).toBe("Try again");
    expect(BACK_TO_DASHBOARD_LABEL).toBe("Back to dashboard");
    expect(REFRESH_STATUS_LABEL).toBe("Refresh status");
  });

  it("keeps the sign-in test privacy notice short and non-legal", () => {
    expect(TEST_PRIVACY_NOTICE_TITLE).toBe("Development and test notice");
    expect(TEST_PRIVACY_NOTICE_COPY).toContain("development/test system");
    expect(TEST_PRIVACY_NOTICE_COPY).toContain("explicitly connect a mailbox");
    expect(TEST_PRIVACY_NOTICE_COPY).toContain("configured AI provider");
    expect(TEST_PRIVACY_NOTICE_COPY).toContain("test or non-sensitive mailbox");
  });
});
