import { friendlyAttachmentType } from "../../lib/attachmentType";

type AttachmentTypeIconProps = {
  filename: string;
  mediaType: string;
};

export function AttachmentTypeIcon({ filename, mediaType }: AttachmentTypeIconProps) {
  const type = friendlyAttachmentType(filename, mediaType);
  return (
    <span
      className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-slate-100 text-xs font-semibold text-slate-700"
      aria-hidden="true"
    >
      {type === "Other" ? "FILE" : type.slice(0, 3)}
    </span>
  );
}
