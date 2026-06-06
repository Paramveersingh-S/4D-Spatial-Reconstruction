/**
 * useVideoProcessing Hook
 * Encapsulates the complete video upload → process → poll → result lifecycle.
 */
import { useState, useCallback, useRef, useEffect } from "react";
import {
  uploadVideo,
  triggerProcessing,
  getJobStatus,
  getResults,
  createStatusWebSocket,
  type JobStatus,
  type JobStatusResponse,
  type ProcessingResultResponse,
  type VideoUploadResponse,
  ApiError,
} from "../lib/api";

// Map backend status to pipeline step index
const STATUS_TO_STEP: Record<string, number> = {
  pending: 0,
  uploading: 0,
  uploaded: 0,
  processing: 0,
  extracting_frames: 1,
  extracting_flow: 2,
  reconstructing_4d: 3,
  generating_point_cloud: 4,
  extracting_trajectories: 5,
  compiling_assets: 5,
  completed: 6,
  failed: -1,
  cancelled: -1,
};

// Human-readable step labels
const PIPELINE_LABELS: Record<string, string> = {
  pending: "Preparing pipeline...",
  uploading: "Uploading video to server...",
  uploaded: "Video uploaded — triggering pipeline...",
  processing: "Initializing 4RC engine...",
  extracting_frames: "Extracting video frames with OpenCV...",
  extracting_flow: "Computing optical flow fields using RAFT...",
  reconstructing_4d: "Running 4RC conditional querying over keyframe trajectories...",
  generating_point_cloud: "Compiling point-cloud density maps & depth triangulation...",
  extracting_trajectories: "Extracting motion trajectories & object tracking...",
  compiling_assets: "Generating camera paths and pushing metadata to storage...",
  completed: "Reconstruction complete",
  failed: "Pipeline failed",
  cancelled: "Pipeline cancelled",
};

export interface VideoProcessingState {
  /** Whether a pipeline is currently running */
  isProcessing: boolean;
  /** The uploaded file name */
  uploadedFileName: string | null;
  /** The video ID returned by the backend */
  videoId: string | null;
  /** Current job status from the backend */
  status: JobStatus | null;
  /** Progress percentage (0-100) */
  progress: number;
  /** Current human-readable step label */
  currentStepLabel: string;
  /** Current step index (0-6) */
  currentStepIndex: number;
  /** Total number of pipeline steps */
  totalSteps: number;
  /** Error message if pipeline failed */
  error: string | null;
  /** Processing results when completed */
  result: ProcessingResultResponse | null;
  /** Whether we're connected to the backend */
  backendConnected: boolean;
}

export interface UseVideoProcessingReturn extends VideoProcessingState {
  /** Upload and process a video file */
  processVideo: (file: File) => Promise<void>;
  /** Reset the processing state */
  reset: () => void;
  /** Whether we're using fallback simulation mode */
  isSimulationMode: boolean;
}

export function useVideoProcessing(): UseVideoProcessingReturn {
  const [state, setState] = useState<VideoProcessingState>({
    isProcessing: false,
    uploadedFileName: null,
    videoId: null,
    status: null,
    progress: 0,
    currentStepLabel: "",
    currentStepIndex: 0,
    totalSteps: 6,
    error: null,
    result: null,
    backendConnected: false,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [isSimulationMode, setIsSimulationMode] = useState(false);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, []);

  const updateFromJobStatus = useCallback((jobStatus: JobStatusResponse) => {
    const stepIndex = STATUS_TO_STEP[jobStatus.status] ?? 0;
    const label = PIPELINE_LABELS[jobStatus.status] ?? jobStatus.current_step ?? "";

    setState((prev) => ({
      ...prev,
      status: jobStatus.status,
      progress: jobStatus.progress,
      currentStepLabel: label,
      currentStepIndex: stepIndex,
      error: jobStatus.error_message,
    }));

    // If completed, fetch results
    if (jobStatus.status === "completed" && jobStatus.video_id) {
      fetchResults(jobStatus.video_id);
    }

    // If terminal state, stop polling
    if (["completed", "failed", "cancelled"].includes(jobStatus.status)) {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }

      if (jobStatus.status === "failed") {
        setState((prev) => ({ ...prev, isProcessing: false }));
      }
    }
  }, []);

  const fetchResults = useCallback(async (videoId: string) => {
    try {
      const results = await getResults(videoId);
      setState((prev) => ({
        ...prev,
        isProcessing: false,
        result: results,
        status: "completed",
        progress: 100,
        currentStepLabel: "Reconstruction complete",
        currentStepIndex: 6,
      }));
    } catch (e) {
      console.error("Failed to fetch results:", e);
      setState((prev) => ({
        ...prev,
        isProcessing: false,
        error: "Failed to fetch results after completion",
      }));
    }
  }, []);

  const startPolling = useCallback(
    (videoId: string) => {
      // Try WebSocket first
      try {
        wsRef.current = createStatusWebSocket(
          videoId,
          (data) => updateFromJobStatus(data as JobStatusResponse),
          () => {
            // WebSocket failed — fall back to polling
            console.warn("WebSocket failed, falling back to HTTP polling");
            startHttpPolling(videoId);
          },
          () => {
            console.log("WebSocket closed");
          }
        );
      } catch {
        // WebSocket not supported — use HTTP polling
        startHttpPolling(videoId);
      }
    },
    [updateFromJobStatus]
  );

  const startHttpPolling = useCallback(
    (videoId: string) => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }

      pollIntervalRef.current = setInterval(async () => {
        try {
          const status = await getJobStatus(videoId);
          updateFromJobStatus(status);
        } catch (e) {
          console.error("Polling error:", e);
        }
      }, 2000); // Poll every 2 seconds
    },
    [updateFromJobStatus]
  );

  // ── Fallback simulation mode when backend is offline ──
  const runSimulation = useCallback(async (fileName: string) => {
    setIsSimulationMode(true);
    setState((prev) => ({
      ...prev,
      isProcessing: true,
      uploadedFileName: fileName,
      videoId: "sim_" + Date.now(),
      status: "processing",
      progress: 0,
      currentStepIndex: 0,
      error: null,
      result: null,
    }));

    const stages: Array<{ status: JobStatus; label: string; duration: number }> = [
      { status: "extracting_frames", label: PIPELINE_LABELS.extracting_frames, duration: 2200 },
      { status: "extracting_flow", label: PIPELINE_LABELS.extracting_flow, duration: 2500 },
      { status: "reconstructing_4d", label: PIPELINE_LABELS.reconstructing_4d, duration: 3000 },
      { status: "generating_point_cloud", label: PIPELINE_LABELS.generating_point_cloud, duration: 2000 },
      { status: "extracting_trajectories", label: PIPELINE_LABELS.extracting_trajectories, duration: 1500 },
      { status: "compiling_assets", label: PIPELINE_LABELS.compiling_assets, duration: 1500 },
    ];

    for (let i = 0; i < stages.length; i++) {
      const stage = stages[i];
      setState((prev) => ({
        ...prev,
        status: stage.status,
        currentStepLabel: stage.label,
        currentStepIndex: i + 1,
        progress: ((i + 1) / stages.length) * 100,
      }));
      await new Promise((r) => setTimeout(r, stage.duration));
    }

    setState((prev) => ({
      ...prev,
      isProcessing: false,
      status: "completed",
      progress: 100,
      currentStepLabel: "Reconstruction complete",
      currentStepIndex: 6,
    }));
  }, []);

  // ── Main entry point ──
  const processVideo = useCallback(
    async (file: File) => {
      setState((prev) => ({
        ...prev,
        isProcessing: true,
        uploadedFileName: file.name,
        status: "uploading",
        progress: 0,
        currentStepLabel: PIPELINE_LABELS.uploading,
        currentStepIndex: 0,
        error: null,
        result: null,
      }));

      try {
        // Step 1: Upload
        const uploadResult: VideoUploadResponse = await uploadVideo(file);

        setState((prev) => ({
          ...prev,
          videoId: uploadResult.video_id,
          status: "uploaded",
          currentStepLabel: PIPELINE_LABELS.uploaded,
          backendConnected: true,
        }));
        setIsSimulationMode(false);

        // Step 2: Trigger processing
        await triggerProcessing(uploadResult.video_id);

        setState((prev) => ({
          ...prev,
          status: "processing",
          currentStepLabel: PIPELINE_LABELS.processing,
        }));

        // Step 3: Start polling for status
        startPolling(uploadResult.video_id);
      } catch (e) {
        if (e instanceof ApiError || (e instanceof TypeError && e.message.includes("fetch"))) {
          // Backend not reachable — fall back to simulation
          console.warn("Backend not reachable — running in simulation mode");
          await runSimulation(file.name);
        } else {
          setState((prev) => ({
            ...prev,
            isProcessing: false,
            error: e instanceof Error ? e.message : "Unknown error",
            status: "failed",
          }));
        }
      }
    },
    [startPolling, runSimulation]
  );

  const reset = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }

    setState({
      isProcessing: false,
      uploadedFileName: null,
      videoId: null,
      status: null,
      progress: 0,
      currentStepLabel: "",
      currentStepIndex: 0,
      totalSteps: 6,
      error: null,
      result: null,
      backendConnected: false,
    });
    setIsSimulationMode(false);
  }, []);

  return {
    ...state,
    processVideo,
    reset,
    isSimulationMode,
  };
}
