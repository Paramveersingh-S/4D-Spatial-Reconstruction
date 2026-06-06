/**
 * API Client for The Impossible Drone Camera Backend.
 * Typed fetch wrappers for all backend endpoints.
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

/**
 * Generic fetch wrapper with error handling.
 */
async function apiFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;

  const response = await fetch(url, {
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...options.headers,
    },
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(
      response.status,
      errorBody.detail || errorBody.error || `HTTP ${response.status}`,
      errorBody
    );
  }

  return response.json();
}

export class ApiError extends Error {
  status: number;
  body: any;

  constructor(status: number, message: string, body?: any) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

// ──────────────────────────────────────────────
// Type Definitions (matching backend schemas)
// ──────────────────────────────────────────────

export type JobStatus =
  | "pending"
  | "uploading"
  | "uploaded"
  | "processing"
  | "extracting_frames"
  | "extracting_flow"
  | "reconstructing_4d"
  | "generating_point_cloud"
  | "extracting_trajectories"
  | "compiling_assets"
  | "completed"
  | "failed"
  | "cancelled";

export interface VideoUploadResponse {
  video_id: string;
  filename: string;
  size_bytes: number;
  storage_path: string;
  status: JobStatus;
  message: string;
}

export interface ProcessingTriggerResponse {
  video_id: string;
  status: JobStatus;
  message: string;
  estimated_time_seconds: number | null;
}

export interface JobStatusResponse {
  video_id: string;
  status: JobStatus;
  progress: number;
  current_step: string | null;
  steps_completed: number;
  total_steps: number;
  created_at: string | null;
  updated_at: string | null;
  error_message: string | null;
  metadata: Record<string, any> | null;
}

export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

export interface TrajectoryPoint {
  t: number;
  x: number;
  y: number;
  z: number;
  heading: number;
  confidence: number;
}

export interface TrackedObjectResult {
  id: string;
  name: string;
  category: string;
  color: string;
  base_speed: number;
  confidence: number;
  trajectory: TrajectoryPoint[];
  bbox_size?: Vec3;
}

export interface PointCloudMetadata {
  num_points: number;
  format: string;
  file_size_bytes: number;
  bounds_min: Vec3;
  bounds_max: Vec3;
  has_colors: boolean;
  has_normals: boolean;
}

export interface ProcessingResultResponse {
  video_id: string;
  status: JobStatus;
  point_cloud_url: string;
  trajectory_url: string;
  tracked_objects: TrackedObjectResult[];
  point_cloud_metadata: PointCloudMetadata;
  total_frames_processed: number;
  processing_time_seconds: number;
  model_version: string;
}

export interface JobListItem {
  video_id: string;
  filename: string;
  status: JobStatus;
  progress: number;
  created_at: string | null;
  tracked_objects_count: number;
}

export interface HealthResponse {
  status: string;
  version: string;
  model_loaded: boolean;
  firebase_connected: boolean;
  gpu_available: boolean;
  device: string;
}

// ──────────────────────────────────────────────
// API Functions
// ──────────────────────────────────────────────

/**
 * Check backend health status.
 */
export async function checkHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/api/v1/health");
}

/**
 * Upload a video file for processing.
 */
export async function uploadVideo(file: File): Promise<VideoUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  return apiFetch<VideoUploadResponse>("/api/v1/upload", {
    method: "POST",
    body: formData,
  });
}

/**
 * Trigger 4RC processing for an uploaded video.
 */
export async function triggerProcessing(
  videoId: string
): Promise<ProcessingTriggerResponse> {
  return apiFetch<ProcessingTriggerResponse>(`/api/v1/process/${videoId}`, {
    method: "POST",
  });
}

/**
 * Get the current status of a processing job.
 */
export async function getJobStatus(videoId: string): Promise<JobStatusResponse> {
  return apiFetch<JobStatusResponse>(`/api/v1/status/${videoId}`);
}

/**
 * Get the results of a completed processing job.
 */
export async function getResults(
  videoId: string
): Promise<ProcessingResultResponse> {
  return apiFetch<ProcessingResultResponse>(`/api/v1/results/${videoId}`);
}

/**
 * List all reconstruction jobs.
 */
export async function listJobs(): Promise<{ jobs: JobListItem[]; total_count: number }> {
  return apiFetch(`/api/v1/jobs`);
}

/**
 * Delete a reconstruction job.
 */
export async function deleteJob(videoId: string): Promise<{ message: string }> {
  return apiFetch(`/api/v1/jobs/${videoId}`, { method: "DELETE" });
}

/**
 * Create a WebSocket connection for real-time status updates.
 */
export function createStatusWebSocket(
  videoId: string,
  onMessage: (data: JobStatusResponse) => void,
  onError?: (error: Event) => void,
  onClose?: () => void
): WebSocket {
  const wsBase = API_BASE_URL.replace("http://", "ws://").replace("https://", "wss://");
  const ws = new WebSocket(`${wsBase}/api/v1/ws/status/${videoId}`);

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch (e) {
      console.error("Failed to parse WebSocket message:", e);
    }
  };

  ws.onerror = (event) => {
    console.error("WebSocket error:", event);
    onError?.(event);
  };

  ws.onclose = () => {
    onClose?.();
  };

  return ws;
}

/**
 * Get the full URL for a processed file.
 */
export function getFileUrl(videoId: string, filename: string): string {
  return `${API_BASE_URL}/api/v1/files/${videoId}/${filename}`;
}
