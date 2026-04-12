import { Navigate } from "react-router-dom";

export default function ScanPage() {
  return <Navigate to="/ranking?mode=scan" replace />;
}
