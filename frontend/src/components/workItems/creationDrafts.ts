import { createContext } from "react";
import type { Candidate, WorkCreate } from "../../api/workItems";

/** Memory-only recovery, owned by the keyed authenticated application tree. */
export type CreationDrafts = Map<string, { body: WorkCreate; candidate?: Candidate }>;
export const CreationDraftContext = createContext<CreationDrafts | null>(null);
