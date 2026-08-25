type ErrorStateProps = {
  message: string;
  onRetry?: () => void;
};

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800">
      <p>{message}</p>
      {onRetry ? (
        <button
          type="button"
          className="mt-3 text-sm font-medium text-red-900 underline"
          onClick={onRetry}
        >
          Try again
        </button>
      ) : null}
    </div>
  );
}
