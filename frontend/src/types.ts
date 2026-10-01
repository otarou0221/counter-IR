import type { NormalizedRoi } from "./roi";

export type PalletSettings = {
  pallet_id: number;
  pallet_number: number;
  camera_id: string;
  display_name: string;
  enabled: boolean;
  low_stock_threshold_liters: number;
  email_rearm_margin_liters: number;
  plane_roi: NormalizedRoi;
  single_box_labels: string[];
  mixed_box_groups: string[][];
  reference_box_label: string;
};

export type CameraDeviceSettings = {
  camera_id: string;
  display_name: string;
  driver: string;
  ip: string; port: number; width: number; height: number;
  depth_width: number; depth_height: number; fps: number;
  align_depth_to_color: false;
};

export type CameraSettings = CameraDeviceSettings & {
  camera_code: string;
  manufacturer: string | null;
  model_name: string | null;
  serial_number: string | null;
  location_id: number | null;
  factory_name: string | null;
  building_name: string | null;
  floor_name: string | null;
  area_name: string | null;
  mounting_note: string | null;
  camera_service_url: string;
};

export type BoxClassSpec = {
  box_type_id?: number | null;
  label: string;
  width_mm: number;
  depth_mm: number;
  height_mm: number;
};

export type SystemSettings = {
  method: "pallet_plane_2roi";
  cameras: CameraSettings[];
  box_catalog: BoxClassSpec[];
  pallets: PalletSettings[];
  frame_count: number;
  measurement_frame_count: number;
  measurement_concurrency: number;
  warmup_frames: number;
  grid_mm: number;
  pallet_height_mm: number;
  occupied_height_mm: number;
  monitor_interval_seconds: number;
};


export type RoiReferenceCapture = {
  camera_id: string;
  capture_id: string;
  captured_at: string | null;
  rgb_path: string;
};

export type RoiReferenceCatalog = {
  captures: RoiReferenceCapture[];
  floor_captures: SavedCapture[];
  floor_capture_limit: number;
};

export type RoiReferenceChange = {
  reference: RoiReferenceCapture;
  removed_capture_ids: string[];
};

export type CameraCalibrationResponse = {
  camera_id: string;
  calibration_id: string;
};

export type PalletResult = {
  pallet_id: number;
  pallet_number: number;
  camera_id: string;
  volume_liters: number;
  is_low_stock: boolean | null;
  low_stock_threshold_liters: number | null;
  estimated_boxes: number;
  plane_rmse_mm: number;
  protrusion_components: number;
  protrusion_volume_liters: number;
  box_combination: BoxCombinationResult | null;
  plot_path: string | null;
  debug_stages_path: string | null;
};

export type BoxCombinationCandidate = {
  counts: Record<string, number>;
  fitted_volume_liters: number;
  residual_volume_liters: number;
};

export type BoxCombinationResult = {
  solver_backend: "cp-sat";
  best: BoxCombinationCandidate;
  alternatives: BoxCombinationCandidate[];
  ambiguous: boolean;
};

export type Measurement = {
  measurement_id: string;
  camera_runs: {
    camera_id: string;
    measurement_id: string;
    calibration_id: string;
    baseline_capture_id: string;
    current_capture_id: string;
  }[];
  pallets: PalletResult[];
};

export type SavedCapture = {
  capture_id: string;
  camera_id: string;
  purpose: string;
  retention: "persistent" | "transient";
  captured_at: string;
  frame_count: number;
  color_shape: [number, number];
  depth_shape: [number, number];
  rgb_path: string;
};

export type DebugCatalog = {
  camera_id: string;
  floor_captures: SavedCapture[];
  current_captures: SavedCapture[];
  current_has_more: boolean;
  current_capture_limit: number;
};

export type MonitorStatus = {
  running: boolean;
  stopping: boolean;
  interval_seconds: number;
  completed_measurements: number;
  consecutive_errors: number;
  last_started_at: string | null;
  last_finished_at: string | null;
  last_error: string | null;
  last_outcome: "not_run" | "success" | "partial_failure" | "failed";
  last_issues: OperationalIssue[];
  email_notifications_enabled: boolean;
  last_email_sent_at: string | null;
  last_email_error: string | null;
  last_email_issue: OperationalIssue | null;
  last_result: Measurement | null;
};

export type OperationalIssue = {
  category: "camera_connection" | "calibration" | "storage" | "measurement" | "notification" | "system";
  title: string;
  cause: string;
  action: string;
  technical_detail: string;
  occurred_at: string;
  camera_id: string | null;
  action_target: "field_camera" | "settings" | "debug" | null;
};

export type CameraStreamStatus = {
  running: boolean;
  connected: boolean;
  frames_received: number;
  started_at: string | null;
  last_frame_at: string | null;
  error: string | null;
  camera: CameraDeviceSettings | null;
  viewers: number;
  capture_active: boolean;
};

export type SystemStatus = {
  busy: boolean;
  method: "pallet_plane_2roi";
  calibrated_camera_ids: string[];
  monitor: MonitorStatus;
  cameras: CameraStreamStatus[];
  database: {
    enabled: boolean;
    connected: boolean;
    last_saved_at: string | null;
    last_error: string | null;
  };
};

export type DashboardState = "normal" | "low_stock" | "unavailable";

export type FactoryMapSummary = {
  factory_map_id: number;
  display_name: string;
  factory_name: string | null;
  building_name: string | null;
  floor_name: string | null;
  image_width: number;
  image_height: number;
  image_url: string;
};

export type PalletMapPlacement = {
  factory_map_id: number;
  pallet_slot_id: number;
  position_x_ratio: number;
  position_y_ratio: number;
};

export type DashboardPalletState = {
  pallet_slot_id: number;
  pallet_number: number;
  display_name: string;
  state: DashboardState;
  inventory_count: number | null;
  volume_liters: number | null;
  box_counts: Record<string, number> | null;
  low_stock_threshold_liters: number;
  measured_at: string | null;
  placement: PalletMapPlacement | null;
};

export type DashboardCameraState = {
  camera_id: string;
  camera_code: string;
  display_name: string;
  factory_name: string | null;
  building_name: string | null;
  floor_name: string | null;
  area_name: string | null;
  state: DashboardState;
  state_message: string;
  last_success_at: string | null;
  last_failure_at: string | null;
  pallets: DashboardPalletState[];
};

export type FactoryDashboard = {
  generated_at: string;
  monitor_running: boolean;
  measurement_interval_seconds: number;
  maps: FactoryMapSummary[];
  cameras: DashboardCameraState[];
};
