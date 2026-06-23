import { useApp } from "../../context/AppContext";
import { ConfirmDialog } from "./ConfirmDialog";
import { OperatorActionModal } from "./OperatorActionModal";

export function ModalHost() {
  const { confirmMessage, actionModalOpen } = useApp();

  return (
    <>
      {actionModalOpen ? <OperatorActionModal /> : null}
      {confirmMessage ? <ConfirmDialog /> : null}
    </>
  );
}
