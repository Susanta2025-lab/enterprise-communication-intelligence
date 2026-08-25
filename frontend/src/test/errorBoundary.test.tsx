import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AppErrorBoundary } from "../components/feedback/AppErrorBoundary";
import { ProductErrorState } from "../components/feedback/ProductErrorState";
import { AuthStub, createAuthSession } from "./fixtures";

function Boom(): never {
  throw new Error("component stack mailbox-secret smtp foundry");
}

describe("application error boundary", () => {
  it("catches a child render failure and shows a generic safe fallback", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(
      <AppErrorBoundary>
        <Boom />
      </AppErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("This page could not be displayed.");
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to dashboard" })).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("mailbox-secret");
    expect(document.body.textContent).not.toContain("component stack");
    expect(document.body.textContent).not.toContain("smtp foundry");
    consoleError.mockRestore();
  });

  it("does not use the render boundary for ordinary API error UI", () => {
    render(
      <AuthStub session={createAuthSession({ isAuthenticated: true })}>
        <AppErrorBoundary>
          <ProductErrorState
            message="Mailbox is temporarily unavailable."
            retryLabel="Try again"
            showSignIn={false}
            showDashboardLink={false}
            onRetry={() => undefined}
          />
        </AppErrorBoundary>
      </AuthStub>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Mailbox is temporarily unavailable.");
    expect(screen.queryByText("This page could not be displayed.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
