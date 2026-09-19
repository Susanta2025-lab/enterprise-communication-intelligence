import { useId, useState } from "react";

import type {
  BusinessContextCreateRequest,
  BusinessContextType,
} from "../../api/contexts";
import { Button } from "../ui/button";
import {
  CONTEXT_TYPE_OPTIONS,
  DESCRIPTION_MAX,
  REFERENCE_MAX,
  TITLE_MAX,
  contextTypeLabel,
} from "./copy";

type ContextFormValues = BusinessContextCreateRequest;

type ContextFormFieldsProps = {
  initial?: Partial<ContextFormValues>;
  submitLabel: string;
  busy?: boolean;
  onSubmit: (values: ContextFormValues) => Promise<void> | void;
  onCancel: () => void;
};

export function ContextFormFields({
  initial,
  submitLabel,
  busy = false,
  onSubmit,
  onCancel,
}: ContextFormFieldsProps) {
  const titleId = useId();
  const typeId = useId();
  const descriptionId = useId();
  const referenceId = useId();
  const [type, setType] = useState<BusinessContextType>(initial?.type ?? "project");
  const [title, setTitle] = useState(initial?.title ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [reference, setReference] = useState(initial?.reference ?? "");
  const [validation, setValidation] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmedTitle = title.trim();
    if (!trimmedTitle) {
      setValidation("Title is required.");
      return;
    }
    if (trimmedTitle.length > TITLE_MAX) {
      setValidation(`Title must be at most ${TITLE_MAX} characters.`);
      return;
    }
    const trimmedDescription = description.trim();
    if (trimmedDescription.length > DESCRIPTION_MAX) {
      setValidation(`Description must be at most ${DESCRIPTION_MAX} characters.`);
      return;
    }
    const trimmedReference = reference.trim();
    if (trimmedReference.length > REFERENCE_MAX) {
      setValidation(`Reference must be at most ${REFERENCE_MAX} characters.`);
      return;
    }
    setValidation(null);
    await onSubmit({
      type,
      title: trimmedTitle,
      description: trimmedDescription ? trimmedDescription : null,
      reference: trimmedReference ? trimmedReference : null,
    });
  }

  return (
    <form className="mt-4 space-y-4" onSubmit={(event) => void handleSubmit(event)} noValidate>
      {validation ? (
        <p role="alert" className="text-sm text-red-700">
          {validation}
        </p>
      ) : null}
      <label className="flex flex-col gap-1 text-sm" htmlFor={typeId}>
        <span className="font-medium text-slate-700">Type</span>
        <select
          id={typeId}
          className="min-h-11 rounded-md border border-slate-300 bg-white px-3 text-slate-900"
          value={type}
          onChange={(event) => setType(event.target.value as BusinessContextType)}
          disabled={busy}
        >
          {CONTEXT_TYPE_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {contextTypeLabel(option)}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm" htmlFor={titleId}>
        <span className="font-medium text-slate-700">Title</span>
        <input
          id={titleId}
          className="min-h-11 rounded-md border border-slate-300 px-3 text-slate-900"
          value={title}
          maxLength={TITLE_MAX}
          onChange={(event) => setTitle(event.target.value)}
          disabled={busy}
          required
          autoComplete="off"
        />
      </label>
      <label className="flex flex-col gap-1 text-sm" htmlFor={descriptionId}>
        <span className="font-medium text-slate-700">Description (optional)</span>
        <textarea
          id={descriptionId}
          className="min-h-24 rounded-md border border-slate-300 px-3 py-2 text-slate-900"
          value={description}
          maxLength={DESCRIPTION_MAX}
          onChange={(event) => setDescription(event.target.value)}
          disabled={busy}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm" htmlFor={referenceId}>
        <span className="font-medium text-slate-700">Reference (optional)</span>
        <input
          id={referenceId}
          className="min-h-11 rounded-md border border-slate-300 px-3 text-slate-900"
          value={reference}
          maxLength={REFERENCE_MAX}
          onChange={(event) => setReference(event.target.value)}
          disabled={busy}
          autoComplete="off"
        />
      </label>
      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
        <Button
          type="button"
          className="w-full bg-white text-slate-900 ring-1 ring-slate-300 hover:bg-slate-50 sm:w-auto"
          onClick={onCancel}
          disabled={busy}
        >
          Cancel
        </Button>
        <Button type="submit" className="w-full sm:w-auto" disabled={busy} aria-busy={busy}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
