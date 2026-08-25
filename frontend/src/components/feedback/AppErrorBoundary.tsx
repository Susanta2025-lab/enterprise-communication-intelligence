import { Component, type ReactNode } from "react";

import { BACK_TO_DASHBOARD_LABEL } from "../../errors/copy";
import { DASHBOARD_PATH } from "../../navigation/paths";
import { Button } from "../ui/button";

type AppErrorBoundaryProps = {
  children: ReactNode;
};

type AppErrorBoundaryState = {
  hasError: boolean;
};

class AppErrorBoundary extends Component<AppErrorBoundaryProps, AppErrorBoundaryState> {
  state: AppErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): AppErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(): void {
    return;
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return <UnexpectedErrorFallback />;
    }
    return this.props.children;
  }
}

function UnexpectedErrorFallback() {
  return (
    <main className="mx-auto flex min-h-screen max-w-lg flex-col justify-center gap-6 px-4 py-16 sm:px-6">
      <div className="space-y-2">
        <p className="text-sm font-medium uppercase tracking-wide text-slate-500">
          Enterprise Communication Intelligence
        </p>
        <h1 className="text-2xl font-semibold text-slate-900">ECI Platform</h1>
      </div>
      <p role="alert" className="text-sm text-slate-700">
        This page could not be displayed.
      </p>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <Button onClick={() => window.location.reload()}>Reload</Button>
        <a href={DASHBOARD_PATH} className="text-sm font-medium text-slate-800 underline">
          {BACK_TO_DASHBOARD_LABEL}
        </a>
      </div>
    </main>
  );
}

export { AppErrorBoundary };
