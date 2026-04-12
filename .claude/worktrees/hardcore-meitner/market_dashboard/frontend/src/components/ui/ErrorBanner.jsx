import { t } from "../../lib/i18n";


export default function ErrorBanner({ message }) {
  if (!message) {
    return null;
  }

  return <div className="status-message error"><strong>{t("Request Issue")}</strong><span>{t(message)}</span></div>;
}
