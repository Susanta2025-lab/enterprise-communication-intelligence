import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { axe } from "jest-axe";

import { EciMark } from "../components/branding/EciMark";
import { ConnectAnotherAccount } from "../components/connectors/ConnectAnotherAccount";
import { ConnectorLogo } from "../components/connectors/ConnectorLogo";
import { MailboxHeader } from "../components/mailbox/MailboxHeader";

describe("ECI branding marks", () => {
  it("exposes a labeled ECI symbol for shell/header use", () => {
    render(<EciMark className="h-9 w-9" title="ECI" />);
    const mark = screen.getByRole("img", { name: "ECI" });
    expect(mark).toBeInTheDocument();
    expect(mark.querySelector("path")).not.toBeNull();
    expect(mark.querySelector("rect")).not.toBeNull();
  });

  it("supports decorative and app/mono variants without labeled roles when decorative", () => {
    const { rerender } = render(<EciMark decorative variant="app" />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    rerender(<EciMark decorative variant="mono" />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});

describe("connector brand marks", () => {
  it("renders Gmail branding as a decorative mark by default", () => {
    render(<ConnectorLogo provider="gmail" className="h-8 w-8" />);
    const logo = document.querySelector('[data-connector-logo="gmail"]');
    expect(logo).not.toBeNull();
    expect(logo).toHaveAttribute("aria-hidden", "true");
    expect(logo).toHaveAttribute("data-provider", "gmail");
    expect(screen.queryByRole("img", { name: /gmail logo/i })).not.toBeInTheDocument();
  });

  it("renders Outlook branding as a decorative mark by default", () => {
    render(<ConnectorLogo provider="microsoft_graph" className="h-8 w-8" />);
    const logo = document.querySelector('[data-connector-logo="outlook"]');
    expect(logo).not.toBeNull();
    expect(logo).toHaveAttribute("aria-hidden", "true");
    expect(logo).toHaveAttribute("data-provider", "microsoft_graph");
    expect(screen.queryByRole("img", { name: /outlook logo/i })).not.toBeInTheDocument();
  });

  it("labels the logo when it is the only identifying element", () => {
    render(<ConnectorLogo provider="gmail" decorative={false} />);
    expect(screen.getByRole("img", { name: "Gmail logo" })).toBeInTheDocument();
  });

  it("keeps provider action labels unchanged when logos sit beside connect controls", () => {
    render(
      <ConnectAnotherAccount provider="gmail" onConnect={() => undefined} />,
    );
    expect(screen.getByRole("button", { name: "Connect another Gmail account" })).toBeEnabled();
    expect(document.querySelector('[data-connector-logo="gmail"]')).not.toBeNull();
  });

  it("shows a decorative provider mark in the mailbox header beside the title", () => {
    render(
      <MemoryRouter>
        <MailboxHeader title="Gmail mailbox" provider="gmail" />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "Gmail mailbox" })).toBeVisible();
    const logo = document.querySelector('[data-connector-logo="gmail"]');
    expect(logo).not.toBeNull();
    expect(logo).toHaveAttribute("aria-hidden", "true");
  });

  it("has no serious accessibility violations for labeled and decorative marks", async () => {
    const { container } = render(
      <div>
        <EciMark title="ECI" />
        <ConnectorLogo provider="gmail" />
        <ConnectorLogo provider="microsoft_graph" decorative={false} />
      </div>,
    );
    const results = await axe(container);
    expect(results.violations).toEqual([]);
  });
});
