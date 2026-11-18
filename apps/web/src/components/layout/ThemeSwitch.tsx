import { setTheme, useTheme, type ThemeChoice } from "../../app/theme";
import { t, type MessageKey } from "../../lib/i18n";
import { Icon, type IconName } from "../ui/icons";

const THEMES: { value: ThemeChoice; icon: IconName; key: MessageKey }[] = [
  { value: "dark", icon: "moon", key: "theme.dark" },
  { value: "light", icon: "sun", key: "theme.light" },
  { value: "system", icon: "monitor", key: "theme.system" },
];

export function ThemeSwitch() {
  const { choice } = useTheme();
  return (
    <div className="theme-switch" role="group" aria-label={t("theme.label")}>
      {THEMES.map((o) => (
        <button key={o.value} type="button" aria-pressed={choice === o.value} onClick={() => setTheme(o.value)} title={t(o.key)}>
          <Icon name={o.icon} size={16} />
          <span className="visually-hidden">{t(o.key)}</span>
        </button>
      ))}
    </div>
  );
}
