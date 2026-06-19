import { useApp } from "../../context/AppContext";
import { ConfirmDialog } from "./ConfirmDialog";

export function ModalHost() {
  const { confirmMessage } = useApp();

  return confirmMessage ? <ConfirmDialog /> : null;
}
