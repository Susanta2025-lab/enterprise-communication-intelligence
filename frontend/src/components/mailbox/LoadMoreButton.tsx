import { Button } from "../ui/button";

type LoadMoreButtonProps = {
  onClick: () => void;
  busy: boolean;
};

export function LoadMoreButton({ onClick, busy }: LoadMoreButtonProps) {
  return (
    <Button className="w-full sm:w-auto" onClick={onClick} disabled={busy} aria-busy={busy}>
      {busy ? "Loading more" : "Load more"}
    </Button>
  );
}
