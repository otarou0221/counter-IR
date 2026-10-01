import ActionButton from "../ActionButton";
import type { FactoryMapSummary } from "../types";

type Props = {
  maps: FactoryMapSummary[];
  selectedMap: FactoryMapSummary;
  editMode: boolean;
  disabled: boolean;
  disabledReason?: string;
  selectedMarker: number | null;
  onSelectMap: (factoryMapId: number) => void;
  onStartEditing: () => void;
  onSave: () => void;
  onCancel: () => void;
  onRemoveSelected: () => void;
  onDeleteMap: () => void;
};

export default function FactoryMapToolbar(props: Props) {
  return <div className="map-toolbar">
    <label>表示フロア<select value={props.selectedMap.factory_map_id}
      disabled={props.editMode}
      onChange={(event) => props.onSelectMap(Number(event.target.value))}>
      {props.maps.map((item) => <option key={item.factory_map_id} value={item.factory_map_id}>
        {item.display_name}
      </option>)}
    </select></label>
    <div>
      {!props.editMode && <ActionButton disabledReason={props.disabledReason}
        onClick={props.onStartEditing}>配置を編集</ActionButton>}
      {!props.editMode && <ActionButton className="danger" disabledReason={props.disabledReason}
        onClick={props.onDeleteMap}>このマップを削除</ActionButton>}
      {props.editMode && <>
        <ActionButton className="primary" disabledReason={props.disabledReason}
          onClick={props.onSave}>配置を保存</ActionButton>
        <ActionButton disabledReason={props.disabledReason}
          onClick={props.onCancel}>キャンセル</ActionButton>
        <ActionButton disabledReason={!props.selectedMarker ? "マップ上のパレットを選択してください" : undefined}
          onClick={props.onRemoveSelected}>選択パレットを未配置へ戻す</ActionButton>
      </>}
    </div>
  </div>;
}
