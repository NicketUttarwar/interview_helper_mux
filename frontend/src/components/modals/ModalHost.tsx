import { useApp } from "../../context/AppContext";
import { ConfirmDialog } from "./ConfirmDialog";
import { TranscriptReuseEditModal } from "./TranscriptReuseEditModal";

export function ModalHost() {
  const { confirmMessage } = useApp();

  return (
    <>
      {confirmMessage ? <ConfirmDialog /> : null}
      <TranscriptReuseEditModal />
    </>
  );
}
