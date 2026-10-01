import { normalizeBoxLabel } from "./boxCatalog";
import type { BoxClassSpec } from "./types";
import SettingsFieldLabel from "./SettingsFieldLabel";

type Props = {
  catalog: BoxClassSpec[];
  groups: string[][];
  onChange: (groups: string[][]) => void;
};

export default function MixedBoxGroupEditor({ catalog, groups, onChange }: Props) {
  const seed = nextPair(catalog.map((box) => box.label), groups);
  const toggle = (index: number, label: string, checked: boolean) => {
    const current = groups[index];
    const nextGroup = checked
      ? [...current.filter((item) => normalizeBoxLabel(item) !== normalizeBoxLabel(label)), label]
      : current.filter((item) => normalizeBoxLabel(item) !== normalizeBoxLabel(label));
    if (nextGroup.length < 2) return;
    onChange(groups.map((group, groupIndex) => groupIndex === index ? nextGroup : group));
  };
  return <div className="mixed-box-groups">
    <div className="box-rule-heading">
      <h4><SettingsFieldLabel label="複数種類が混在する組み合わせ" /></h4>
      <button type="button" disabled={!seed}
        onClick={() => seed && onChange([...groups, seed])}>＋ 組み合わせを追加</button>
    </div>
    <p className="settings-help">同じパレット上へ同時に存在できる箱を、2種類以上選択します。</p>
    {groups.length === 0 && <span className="empty-box-rule">混在する組み合わせはありません。</span>}
    {groups.map((group, index) => {
      const selected = new Set(group.map(normalizeBoxLabel));
      return <div className="mixed-box-group" key={`${index}:${group.join("|")}`}>
        <strong>組み合わせ {index + 1}</strong>
        <div className="class-options">{catalog.map((box) => <label key={box.label} className="checkbox-field">
          <input type="checkbox" checked={selected.has(normalizeBoxLabel(box.label))}
            onChange={(event) => toggle(index, box.label, event.target.checked)} />{box.label}
        </label>)}</div>
        <button type="button" onClick={() => onChange(groups.filter((_, groupIndex) => groupIndex !== index))}>
          この組み合わせを削除
        </button>
      </div>;
    })}
  </div>;
}

function nextPair(labels: string[], groups: string[][]): string[] | null {
  const existing = new Set(groups.map((group) => (
    group.map(normalizeBoxLabel).sort().join("\u0000")
  )));
  for (let left = 0; left < labels.length; left += 1) {
    for (let right = left + 1; right < labels.length; right += 1) {
      const pair = [labels[left], labels[right]];
      if (!existing.has(pair.map(normalizeBoxLabel).sort().join("\u0000"))) return pair;
    }
  }
  return null;
}
