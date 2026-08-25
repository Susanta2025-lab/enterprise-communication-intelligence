import { ConfirmDialog } from "../connectors/ConfirmDialog";
import { SEND_APPROVED_REPLY_LABEL, SEND_CONFIRM_DESCRIPTION, SEND_CONFIRM_TITLE } from "./copy";

type SendConfirmationDialogProps = {
  open: boolean;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function SendConfirmationDialog({
  open,
  busy,
  onConfirm,
  onCancel,
}: SendConfirmationDialogProps) {
  return (
    <ConfirmDialog
      open={open}
      title={SEND_CONFIRM_TITLE}
      description={SEND_CONFIRM_DESCRIPTION}
      confirmLabel={SEND_APPROVED_REPLY_LABEL}
      confirmDisabled={busy}
      confirmBusy={busy}
      onConfirm={() => {
        if (busy) {
          return;
        }
        onConfirm();
      }}
      onCancel={onCancel}
    />
  );
}
