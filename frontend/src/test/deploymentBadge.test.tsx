import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EciApiClient } from "../api/client";
import { ME_PATH } from "../api/me";
import { CurrentUserProvider } from "../auth/CurrentUserContext";
import { AppShell } from "../components/AppShell";
import { DeploymentBadge } from "../components/DeploymentBadge";
import {
  AuthStub,
  TEST_AWS_DEPLOYMENT,
  TEST_AZURE_DEPLOYMENT,
  TEST_TOKEN,
  createAuthSession,
} from "./fixtures";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderOwnerShell(deployment: typeof TEST_AZURE_DEPLOYMENT | typeof TEST_AWS_DEPLOYMENT) {
  const fetchImpl = vi.fn<typeof fetch>(async (input) => {
    const url = String(input);
    if (url.includes(ME_PATH)) {
      return jsonResponse(200, { application_role: "owner", is_owner: true });
    }
    return jsonResponse(500, { detail: "unexpected" });
  });
  const apiClient = new EciApiClient({
    baseUrl: "http://localhost:8000",
    tokenProvider: { acquireAccessToken: async () => TEST_TOKEN },
    fetchImpl,
  });

  render(
    <AuthStub
      session={createAuthSession({
        isAuthenticated: true,
        accountKey: "home-account-owner",
        displayName: "Ada Lovelace",
      })}
    >
      <CurrentUserProvider apiClient={apiClient}>
        <AppShell deployment={deployment}>content</AppShell>
      </CurrentUserProvider>
    </AuthStub>,
  );
}

describe("DeploymentBadge", () => {
  it("renders Azure cloud, Foundry, and Spain Central with official links", () => {
    render(
      <DeploymentBadge
        cloudProvider="azure"
        aiProvider="microsoft_foundry"
        cloudRegion="Spain Central"
      />,
    );

    const badge = screen.getByTestId("deployment-badge");
    expect(within(badge).getByTestId("deployment-cloud-label")).toHaveTextContent("Azure");

    const details = screen.getByTestId("deployment-details");
    expect(details).toHaveTextContent("Azure");
    expect(details).toHaveTextContent("Microsoft Foundry");
    expect(details).toHaveTextContent("Spain Central");
    expect(details).not.toHaveTextContent("Amazon Bedrock");
    expect(details).not.toHaveTextContent("eu-south-2");

    const cloudLink = screen.getByTestId("deployment-cloud-link");
    expect(cloudLink).toHaveAttribute("href", "https://azure.microsoft.com/");
    expect(cloudLink).toHaveAttribute("target", "_blank");
    expect(cloudLink).toHaveAttribute("rel", "noopener noreferrer");

    const aiLink = screen.getByTestId("deployment-ai-link");
    expect(aiLink).toHaveAttribute("href", "https://azure.microsoft.com/products/ai-foundry/");
    expect(aiLink).toHaveAttribute("target", "_blank");
    expect(aiLink).toHaveAttribute("rel", "noopener noreferrer");

    expect(screen.getByTestId("deployment-region")).toHaveTextContent("Spain Central");
  });

  it("renders AWS cloud, Bedrock, and eu-south-2 with official links", () => {
    render(
      <DeploymentBadge
        cloudProvider="aws"
        aiProvider="amazon_bedrock"
        cloudRegion="eu-south-2"
      />,
    );

    expect(screen.getByTestId("deployment-cloud-label")).toHaveTextContent("AWS");

    const details = screen.getByTestId("deployment-details");
    expect(details).toHaveTextContent("AWS");
    expect(details).toHaveTextContent("Amazon Bedrock");
    expect(details).toHaveTextContent("eu-south-2");
    expect(details).not.toHaveTextContent("Microsoft Foundry");
    expect(details).not.toHaveTextContent("Spain Central");

    const cloudLink = screen.getByTestId("deployment-cloud-link");
    expect(cloudLink).toHaveAttribute("href", "https://aws.amazon.com/");
    expect(cloudLink).toHaveAttribute("target", "_blank");
    expect(cloudLink).toHaveAttribute("rel", "noopener noreferrer");

    const aiLink = screen.getByTestId("deployment-ai-link");
    expect(aiLink).toHaveAttribute("href", "https://aws.amazon.com/bedrock/");
    expect(aiLink).toHaveAttribute("target", "_blank");
    expect(aiLink).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("does not introduce vendor logos", () => {
    const { container } = render(
      <DeploymentBadge
        cloudProvider="aws"
        aiProvider="amazon_bedrock"
        cloudRegion="eu-south-2"
      />,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("[data-vendor-logo]")).toBeNull();
  });
});

describe("owner shell deployment indicator", () => {
  it("shows Platform Owner badge and Azure deployment indicator for owners", async () => {
    renderOwnerShell(TEST_AZURE_DEPLOYMENT);
    expect(await screen.findByTestId("owner-badge")).toHaveTextContent("Platform Owner");
    expect(screen.getByTestId("deployment-badge")).toBeInTheDocument();
    expect(screen.getByTestId("deployment-cloud-label")).toHaveTextContent("Azure");
  });

  it("shows Platform Owner badge and AWS deployment indicator for owners", async () => {
    renderOwnerShell(TEST_AWS_DEPLOYMENT);
    expect(await screen.findByTestId("owner-badge")).toHaveTextContent("Platform Owner");
    expect(screen.getByTestId("deployment-cloud-label")).toHaveTextContent("AWS");
  });

  it("does not show the deployment indicator for ordinary users", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      if (url.includes(ME_PATH)) {
        return jsonResponse(200, { application_role: "user", is_owner: false });
      }
      return jsonResponse(500, { detail: "unexpected" });
    });
    const apiClient = new EciApiClient({
      baseUrl: "http://localhost:8000",
      tokenProvider: { acquireAccessToken: async () => TEST_TOKEN },
      fetchImpl,
    });

    render(
      <AuthStub
        session={createAuthSession({
          isAuthenticated: true,
          accountKey: "home-account-1",
          displayName: "Ada Lovelace",
        })}
      >
        <CurrentUserProvider apiClient={apiClient}>
          <AppShell deployment={TEST_AZURE_DEPLOYMENT}>content</AppShell>
        </CurrentUserProvider>
      </AuthStub>,
    );

    expect(await screen.findByTestId("signed-in-account")).toHaveTextContent("Ada Lovelace");
    expect(screen.queryByTestId("owner-badge")).not.toBeInTheDocument();
    expect(screen.queryByTestId("deployment-badge")).not.toBeInTheDocument();
  });
});
