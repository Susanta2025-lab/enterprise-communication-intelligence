import { useAuth } from "../auth/AuthContext";
import { SIGN_IN_LABEL } from "../errors/copy";
import { Button } from "./ui/button";

export function SignInPanel() {
  const { login, error, interactionInProgress } = useAuth();

  return (
    <main className="mx-auto flex min-h-screen max-w-lg flex-col justify-center gap-6 px-4 py-16 sm:px-6">
      <div className="space-y-2">
        <p className="text-sm font-medium uppercase tracking-wide text-slate-500">
          Enterprise Communication Intelligence
        </p>
        <h1 className="text-3xl font-semibold text-slate-900">ECI Platform</h1>
        <p className="text-slate-600">Sign in with your ECI identity to continue.</p>
      </div>
      <div>
        <Button className="w-full sm:w-auto" onClick={() => void login()} disabled={interactionInProgress}>
          {SIGN_IN_LABEL}
        </Button>
      </div>
      {error ? (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      ) : null}
    </main>
  );
}
