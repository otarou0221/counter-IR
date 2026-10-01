import type { NavigationTarget } from "./routes";

const labels: Record<NavigationTarget, string> = {
  map: "工場マップ",
  field: "現場用",
  settings: "設定",
  debug: "保守・診断",
};

export default function Navigation({ target, onChange }: {
  target: NavigationTarget;
  onChange: (target: NavigationTarget) => void;
}) {
  return <nav className="page-navigation" aria-label="画面切り替え">
    {(Object.keys(labels) as NavigationTarget[]).map((item) => <button key={item}
      className={target === item ? "selected" : ""} onClick={() => onChange(item)}>{labels[item]}</button>)}
  </nav>;
}
