import { useApp } from "../../context/AppContext";
import { ConfirmDialog } from "./ConfirmDialog";
import { OperatorActionModal } from "./OperatorActionModal";

export function ModalHost() {
  const { actionModalOpen, confirmMessage } = useApp();

  return (
    <>
      {confirmMessage ? <ConfirmDialog /> : null}
      {actionModalOpen ? <OperatorActionModal /> : null}
    </>
  );
}
