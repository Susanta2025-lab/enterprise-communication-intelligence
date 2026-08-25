import { forwardRef } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import {
  BACK_TO_DASHBOARD_LABEL,
  SIGN_IN_LABEL,
} from "../../errors/copy";
import type { ProductErrorPresentation } from "../../errors/presentProductError";
import { DASHBOARD_PATH } from "../../navigation/paths";
import { Button } from "../ui/button";

type ProductErrorStateProps = ProductErrorPresentation & {
  onRetry?: () => void;
};

export const ProductErrorState = forwardRef<HTMLDivElement, ProductErrorStateProps>(
  function ProductErrorState(
    { message, retryLabel, showSignIn, showDashboardLink, onRetry },
    ref,
  ) {
    const { login, interactionInProgress } = useAuth();
    const hasActions = showSignIn || Boolean(onRetry && retryLabel) || showDashboardLink;

    return (
      <div
        ref={ref}
        role="alert"
        tabIndex={-1}
        className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800 focus:outline focus:outline-2 focus:outline-offset-2 focus:outline-red-800"
      >
        <p className="min-w-0 break-words">{message}</p>
        {hasActions ? (
          <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
            {showSignIn ? (
              <Button onClick={() => void login()} disabled={interactionInProgress}>
                {SIGN_IN_LABEL}
              </Button>
            ) : null}
            {onRetry && retryLabel ? <Button onClick={onRetry}>{retryLabel}</Button> : null}
            {showDashboardLink ? (
              <Link
                to={DASHBOARD_PATH}
                className="text-sm font-medium text-red-900 underline"
              >
                {BACK_TO_DASHBOARD_LABEL}
              </Link>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  },
);
