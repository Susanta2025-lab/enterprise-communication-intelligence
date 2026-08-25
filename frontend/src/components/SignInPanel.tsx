import { useAuth } from "../auth/AuthContext";
import { Button } from "./ui/button";

export function SignInPanel() {
  const { login, error, interactionInProgress } = useAuth();

  return (
    <main className="mx-auto flex min-h-screen max-w-lg flex-col justify-center gap-6 px-6 py-16">
      <div className="space-y-2">
        <p className="text-sm font-medium uppercase tracking-wide text-slate-500">
          Enterprise Communication Intelligence
        </p>
        <h1 className="text-3xl font-semibold text-slate-900">ECI Platform</h1>
        <p className="text-slate-600">Sign in with your ECI identity to continue.</p>
      </div>
      <div>
        <Button onClick={() => void login()} disabled={interactionInProgress}>
          Sign in
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
