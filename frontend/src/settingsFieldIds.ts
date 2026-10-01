function idPart(value: string | number): string {
  return encodeURIComponent(String(value));
}

export const settingsSectionIds = {
  cameras: "settings-camera-section",
  boxes: "settings-box-section",
  pallets: "settings-pallet-section",
  measurement: "settings-measurement-section",
} as const;

export const settingsFieldId = {
  camera: (cameraId: string, field: string) => (
    `settings-camera-${idPart(cameraId)}-${idPart(field)}`
  ),
  box: (index: number, field: string) => `settings-box-${index}-${idPart(field)}`,
  pallet: (palletId: number, field: string) => `settings-pallet-${palletId}-${idPart(field)}`,
  measurement: (field: string) => `settings-measurement-${idPart(field)}`,
};
