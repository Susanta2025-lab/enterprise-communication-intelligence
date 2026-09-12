import type { ReactNode } from "react";

import { useAuth } from "../auth/AuthContext";
import { useCurrentUser } from "../auth/useCurrentUser";
import { ECI_CYAN, ECI_NAVY } from "./branding/eciBrand";
import { EciMark } from "./branding/EciMark";
import { Button } from "./ui/button";

const DEVELOPER_LINKEDIN_URL = "https://www.linkedin.com/in/susantahazra";
const DEVELOPER_GITHUB_URL = "https://github.com/Susanta2025-lab";

const attributionLinkClassName =
  "rounded-sm text-slate-500 underline-offset-2 transition-colors hover:text-slate-700 hover:underline focus-visible:text-slate-700";

type AppShellProps = {
  children: ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  const { displayName, logout, error, interactionInProgress } = useAuth();
  const { isOwner } = useCurrentUser();

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl min-w-0 flex-col gap-4 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <EciMark className="h-10 w-10 shrink-0" title="ECI" />
            <div className="min-w-0">
              <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                Enterprise Communication Intelligence
              </p>
              <h1 className="text-lg font-semibold" style={{ color: ECI_NAVY }}>
                ECI Platform
              </h1>
              <p
                className="mt-0.5 text-sm tracking-wide text-slate-600"
                data-testid="eci-tagline"
              >
                Register. Connect. Analyze.
              </p>
            </div>
          </div>
          <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              {displayName ? (
                <p className="min-w-0 break-words text-sm text-slate-600" data-testid="signed-in-account">
                  Signed in as {displayName}
                </p>
              ) : (
                <p className="text-sm text-slate-600">Signed in</p>
              )}
              {isOwner ? (
                <span
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-full border bg-cyan-50 px-2.5 py-0.5 text-xs font-semibold shadow-sm"
                  style={{ color: ECI_NAVY, borderColor: "rgba(8, 43, 89, 0.55)" }}
                  data-testid="owner-badge"
                >
                  <span
                    className="h-1.5 w-1.5 shrink-0 rounded-full"
                    style={{ backgroundColor: ECI_CYAN }}
                    aria-hidden="true"
                  />
                  Platform Owner
                </span>
              ) : null}
            </div>
            <Button className="w-full sm:w-auto" onClick={() => void logout()} disabled={interactionInProgress}>
              Sign out
            </Button>
          </div>
        </div>
      </header>
      <main id="main-content" className="mx-auto w-full max-w-6xl min-w-0 flex-1 px-4 py-8 sm:px-6">
        {error ? (
          <p role="alert" className="mb-4 text-sm text-red-700">
            {error}
          </p>
        ) : null}
        {children}
      </main>
      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto max-w-6xl px-4 py-3 sm:px-6">
          <p className="text-center text-xs text-slate-500" data-testid="eci-attribution">
            Designed & developed by{" "}
            <a
              href={DEVELOPER_LINKEDIN_URL}
              target="_blank"
              rel="noopener noreferrer"
              className={attributionLinkClassName}
              aria-label="Susanta Hazra on LinkedIn"
            >
              Susanta Hazra
            </a>
            {" · "}
            <a
              href={DEVELOPER_GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className={attributionLinkClassName}
            >
              GitHub
            </a>
          </p>
        </div>
      </footer>
    </div>
  );
}
