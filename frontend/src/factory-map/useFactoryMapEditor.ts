import { useMemo, useState } from "react";
import type { FactoryMapSummary } from "../types";
import type { PalletMarker } from "./presentation";

export type MapPosition = { x: number; y: number };

export function useFactoryMapEditor(
  markers: PalletMarker[],
  selectedMap: FactoryMapSummary | null,
) {
  const [editMode, setEditMode] = useState(false);
  const [draft, setDraft] = useState<Record<string, MapPosition>>({});
  const [selectedMarker, setSelectedMarker] = useState<number | null>(null);

  const savedPositions = useMemo(() => Object.fromEntries(
    markers.filter(({ pallet }) => (
      pallet.placement?.factory_map_id === selectedMap?.factory_map_id
    )).map(({ pallet }) => [pallet.pallet_slot_id, {
        x: (pallet.placement?.position_x_ratio ?? 0.5) * (selectedMap?.image_width ?? 1),
        y: (pallet.placement?.position_y_ratio ?? 0.5) * (selectedMap?.image_height ?? 1),
      }]),
  ), [markers, selectedMap]);

  const startEditing = () => {
    setDraft(savedPositions);
    setSelectedMarker(null);
    setEditMode(true);
  };
  const cancelEditing = () => {
    setDraft({});
    setSelectedMarker(null);
    setEditMode(false);
  };
  const finishSaving = () => {
    setSelectedMarker(null);
    setEditMode(false);
  };
  const setPosition = (palletSlotId: number, position: MapPosition) => {
    setDraft((current) => ({ ...current, [palletSlotId]: position }));
    setSelectedMarker(palletSlotId);
  };
  const removeSelected = () => {
    if (!selectedMarker) return;
    setDraft((current) => {
      const updated = { ...current };
      delete updated[selectedMarker];
      return updated;
    });
    setSelectedMarker(null);
  };

  return {
    editMode,
    draft,
    positions: editMode ? draft : savedPositions,
    selectedMarker,
    setSelectedMarker,
    startEditing,
    cancelEditing,
    finishSaving,
    setPosition,
    removeSelected,
  };
}
