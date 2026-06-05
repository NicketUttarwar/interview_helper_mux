import { useApp } from "../../context/AppContext";
import { ApiConsentModal } from "../ApiConsentModal";
import { ConfirmDialog } from "./ConfirmDialog";
import { OperatorActionModal } from "./OperatorActionModal";
import { StageTransitionModal } from "./StageTransitionModal";
import { Toast } from "../Toast";

export function ModalHost() {
  const { actionModalOpen, confirmMessage } = useApp();

  return (
    <>
      <Toast />
      <ApiConsentModal />
      {confirmMessage ? <ConfirmDialog /> : null}
      <StageTransitionModal />
      {actionModalOpen ? <OperatorActionModal /> : null}
    </>
  );
}
