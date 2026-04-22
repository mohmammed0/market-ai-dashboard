import { ToastProvider } from "./components/ui/Toast";
import AppRoutes from "./app/AppRoutes";

export default function App() {
  return (
    <ToastProvider>
      <AppRoutes />
    </ToastProvider>
  );
}
