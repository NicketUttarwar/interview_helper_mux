import { useApp } from "../../context/AppContext";
import { ConfirmDialog } from "./ConfirmDialog";
import { OperatorActionModal } from "./OperatorActionModal";
import { StageTransitionModal } from "./StageTransitionModal";
import { Toast } from "../Toast";

export function ModalHost() {
  const { actionModalOpen, confirmMessage } = useApp();

  return (
    <>
      <Toast />
      {confirmMessage ? <ConfirmDialog /> : null}
      <StageTransitionModal />
      {actionModalOpen ? <OperatorActionModal /> : null}
    </>
  );
}
