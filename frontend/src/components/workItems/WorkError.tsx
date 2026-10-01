import { Link } from "react-router-dom";
import { EciApiError } from "../../api/errors";
import { ownedWorkLocation } from "../../api/workItems";
export function WorkError({ error, retry }: { error: unknown; retry?: () => void }) {
  if (!error) return null;
  let message = "The request could not be completed. Retry the same request safely.";
  let location: string | null = null;
  if (error instanceof EciApiError) {
    location = ownedWorkLocation(error.location);
    if (error.status === 401) message = "Sign in again to continue.";
    if (error.status === 403) message = "Your account is missing a required permission.";
    if (error.status === 404) message = "This item or persisted source is unavailable.";
    if (error.status === 422) message = "Review the fields, due value and context before retrying.";
    if (error.status === 409) message = "The saved state conflicts with this request. Reload and review before making another change.";
    if (error.code === "work_item_context_archived") message = "This context is archived. Choose an active context or leave the item unassociated.";
    if (error.code === "work_item_invalid_transition") message = "This lifecycle change is no longer permitted. Reload and review the current state.";
    if (error.code === "work_item_candidate_changed") message = "This observation changed. Close this review and reload the candidates.";
    if (error.code === "work_item_candidate_already_tracked") message = "This exact observation is already tracked.";
    if (error.code === "work_item_creation_key_conflict") message = "This creation key was used with different fields. Recover the original request before starting another item.";
  }
  return <div role="alert" className="rounded border border-red-300 p-3"><p>{message}</p>{location && <Link className="underline" to={location}>Open existing tracked item</Link>}{retry && <button type="button" onClick={retry}>Reload and review</button>}</div>;
}
