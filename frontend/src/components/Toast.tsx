import { useApp } from "../context/AppContext";

export function Toast() {
  const { toast } = useApp();
  if (!toast) return null;
  return <div className="toast">{toast}</div>;
}
