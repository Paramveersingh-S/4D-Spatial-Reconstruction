/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useEffect, useRef, useTransition, ChangeEvent } from "react";
import {
  Compass,
  Cpu,
  Database,
  Activity,
  Layers,
  Play,
  Pause,
  Upload,
  Layers3,
  Video,
  Monitor,
  RefreshCw,
  Gauge,
  ChevronsRight,
  CheckCircle2,
  AlertCircle,
  FolderOpen,
  Wifi,
  Download,
  Flame,
  MousePointer
} from "lucide-react";
import THREE_CANVAS_EXPORT from "./components/ThreeCanvas";
import { TRACKED_OBJECTS, PROCESS_STEPS_TEMPLATE } from "./data";
import { ProcessingStep, TrackedObject } from "./types";

export default function App() {
  // Navigation / Interactive States
  const [currentTime, setCurrentTime] = useState<number>(3.5); // Starts mid-way to show active movement immediately
  const [selectedObjectId, setSelectedObjectId] = useState<string | null>("obj-fpv-drone");
  const [cameraMode, setCameraMode] = useState<"free" | "follow" | "fpv">("follow");
  const [isPlaying, setIsPlaying] = useState<boolean>(true);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1);
  const [showGhostPaths, setShowGhostPaths] = useState<boolean>(true);
  const [pointConfidenceFilter, setPointConfidenceFilter] = useState<number>(85);

  // Video Upload & 4RC FastAPI Ingestion Pipeline Simulator
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
  const [pipelineSteps, setPipelineSteps] = useState<ProcessingStep[]>(PROCESS_STEPS_TEMPLATE);
  const [currentStepIdx, setCurrentStepIdx] = useState<number>(0);
  const [reconstructedCount, setReconstructedCount] = useState<number>(4);

  // Selected Clip
  const [activeClipName, setActiveClipName] = useState<string>("Urban Crossroads Sweep v4.1");

  const [isPending, startTransition] = useTransition();

  // Reference for requestAnimationFrame loops
  const requestRef = useRef<number | null>(null);
  const lastTimeRef = useRef<number>(performance.now());

  // Master timeline duration: 0s to 12s
  const MAX_TIME = 12.0;

  // Auto playback clock loop
  useEffect(() => {
    if (isPlaying) {
      const updateFrame = () => {
        const now = performance.now();
        const delta = (now - lastTimeRef.current) / 1000;
        lastTimeRef.current = now;

        setCurrentTime((prev) => {
          let next = prev + delta * playbackSpeed;
          if (next >= MAX_TIME) {
            next = 0; // seamless Loop
          }
          return next;
        });

        requestRef.current = requestAnimationFrame(updateFrame);
      };
      lastTimeRef.current = performance.now();
      requestRef.current = requestAnimationFrame(updateFrame);
    } else {
      if (requestRef.current) {
        cancelAnimationFrame(requestRef.current);
      }
    }

    return () => {
      if (requestRef.current) {
        cancelAnimationFrame(requestRef.current);
      }
    };
  }, [isPlaying, playbackSpeed]);

  // Handle uploading simulation
  const handleFileUpload = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    triggerPipelineSimulation(file.name);
  };

  const triggerPipelineSimulation = (fileName: string) => {
    setIsProcessing(true);
    setUploadedFileName(fileName);
    setCurrentStepIdx(0);

    // Reset steps
    setPipelineSteps(
      PROCESS_STEPS_TEMPLATE.map((step, idx) => ({
        ...step,
        status: idx === 0 ? "processing" : "pending",
      }))
    );

    // Run interval simulating different steps of FastAPI 4RC backend
    let step = 0;
    const interval = setInterval(() => {
      setPipelineSteps((prev) => {
        const updated = [...prev];
        // Complete current step
        updated[step].status = "completed";
        // Start next step if exists
        if (step + 1 < updated.length) {
          updated[step + 1].status = "processing";
        }
        return updated;
      });

      step++;
      setCurrentStepIdx(step);

      if (step >= PROCESS_STEPS_TEMPLATE.length) {
        clearInterval(interval);
        setTimeout(() => {
          setIsProcessing(false);
          setActiveClipName(fileName);
          setReconstructedCount((c) => c + 1);
          // Set to active tracking
          setSelectedObjectId("obj-fpv-drone");
          setCameraMode("follow");
          setCurrentTime(0);
        }, 1000);
      }
    }, 2200);
  };

  // Pre-load preset environment clips
  const presets = [
    { name: "Urban Crossroads Sweep v4.1", objects: 4, points: "8,430 px" },
    { name: "Suburban Freeway Transit D4R", objects: 3, points: "6,210 px" },
    { name: "Downtown Skyway Sweep 4RC", objects: 5, points: "11,540 px" }
  ];

  // Get active selected object
  const selectedObject = TRACKED_OBJECTS.find((o) => o.id === selectedObjectId) || null;
  const objectPos = selectedObject ? selectedObject.getPosition(currentTime) : { x: 0, y: 0, z: 0 };
  const objectHeadingDeg = selectedObject ? (selectedObject.getHeading(currentTime) * 180) / Math.PI : 0;

  return (
    <div id="main-root-container" className="min-h-screen bg-slate-950 font-sans text-slate-100 flex flex-col antialiased">
      {/* 1. Header Toolbar */}
      <header id="nav-header" className="border-b border-slate-900 bg-slate-950/90 backdrop-blur-md px-6 py-4 flex flex-col md:flex-row md:items-center justify-between gap-4 sticky top-0 z-50">
        <div className="flex items-center gap-3">
          <div className="bg-gradient-to-tr from-cyan-500 to-purple-600 p-2.5 rounded-lg shadow-lg shadow-cyan-500/20">
            <Flame className="h-6 w-6 text-white animate-pulse" />
          </div>
          <div>
            <span className="text-[10px] uppercase tracking-[0.25em] text-cyan-400 font-mono font-semibold">Vertex AI &amp; 4RC Engine</span>
            <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              The Impossible Drone Camera <span className="text-xs bg-slate-800 text-slate-400 px-2 py-0.5 rounded border border-slate-700 font-mono">v4.0_4D</span>
            </h1>
          </div>
        </div>

        {/* Realtime System Telemetry Displays */}
        <div className="flex items-center flex-wrap gap-4 md:gap-6 font-mono text-[11px] bg-slate-900/60 p-2 rounded-lg border border-slate-800/80">
          <div className="flex items-center gap-2 px-2 py-1 bg-slate-950/80 rounded border border-slate-800">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <span className="text-slate-400">FASTAPI PORT:</span>
            <span className="text-white font-bold">3000 (MOCK)</span>
          </div>

          <div className="flex items-center gap-1.5">
            <Activity className="h-3.5 w-3.5 text-cyan-400" />
            <span className="text-slate-400">LATENCY:</span>
            <span className="text-cyan-400 font-bold">31ms</span>
          </div>

          <div className="flex items-center gap-1.5">
            <Database className="h-3.5 w-3.5 text-purple-400" />
            <span className="text-slate-400">FIRESTORE:</span>
            <span className="text-purple-400 font-bold">CONNECTED</span>
          </div>

          <div className="flex items-center gap-1.5">
            <Layers className="h-3.5 w-3.5 text-emerald-400" />
            <span className="text-slate-400">SPATIAL DENSITY:</span>
            <span className="text-emerald-400 font-bold">DENSE_PLY</span>
          </div>
        </div>
      </header>

      {/* 2. Primary Layout Grid */}
      <main id="dashboard-grid" className="flex-1 grid grid-cols-1 xl:grid-cols-4 gap-6 p-6 overflow-hidden">
        {/* Left Hand: Ingestion & Processing Control */}
        <div id="left-sidebar" className="xl:col-span-1 flex flex-col gap-6">
          {/* Section A: Live Video Upload & 4RC Trigger */}
          <div className="bg-slate-900/40 backdrop-blur-md rounded-xl p-5 border border-slate-800 flex flex-col gap-4">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
              <h2 className="text-sm font-semibold tracking-wide text-cyan-400 uppercase flex items-center gap-2">
                <Video className="h-4 w-4" /> Raw Video Ingestion
              </h2>
              <span className="text-[10px] font-mono text-slate-500">FastAPI &amp; PubSub</span>
            </div>

            <p className="text-xs text-slate-400 leading-relaxed">
              Upload any raw MP4 drone visual sequence. The backend spins up on Google Cloud Run to compile the coordinates into a dense 4D PLY point cloud model.
            </p>

            {/* Custom file trigger target box */}
            <label className="border border-dashed border-slate-700 hover:border-cyan-500 hover:bg-cyan-500/5 transition duration-200 rounded-lg p-5 flex flex-col items-center justify-center gap-2.5 cursor-pointer relative group">
              <input
                type="file"
                accept="video/mp4,video/x-m4v,video/*"
                className="hidden"
                onChange={handleFileUpload}
                disabled={isProcessing}
              />
              <div className="p-3 bg-slate-800 rounded-full group-hover:bg-cyan-950/50 transition">
                <Upload className="h-5 w-5 text-slate-400 group-hover:text-cyan-400" />
              </div>
              <div className="text-center">
                <span className="text-xs text-white font-medium block">Select RGB Drone Clip</span>
                <span className="text-[10px] text-slate-500">MP4, MOV (Max 50MB)</span>
              </div>
            </label>

            {/* Ingestion Pipeline Logs Timeline */}
            {(isProcessing || uploadedFileName) && (
              <div className="bg-slate-950/80 rounded-lg p-4 border border-slate-800 flex flex-col gap-3 font-mono text-[11px]">
                <div className="flex items-center justify-between text-xs font-semibold text-slate-400 pb-1.5 border-b border-slate-900">
                  <span className="truncate max-w-[150px]">🗂️ {uploadedFileName}</span>
                  {isProcessing ? (
                    <span className="text-cyan-400 flex items-center gap-1 animate-pulse">
                      <RefreshCw className="h-3 w-3 animate-spin" /> RUNNING
                    </span>
                  ) : (
                    <span className="text-emerald-400 flex items-center gap-1">
                      <CheckCircle2 className="h-3.5 w-3.5" /> RECONSTRUCTED
                    </span>
                  )}
                </div>

                <div className="flex flex-col gap-2.5">
                  {pipelineSteps.map((step, idx) => {
                    const isDone = idx < currentStepIdx;
                    const isActive = idx === currentStepIdx && isProcessing;
                    const isUpcoming = idx > currentStepIdx || (!isProcessing && !isDone);

                    return (
                      <div
                        key={step.id}
                        className={`flex gap-2 items-start transition-colors duration-200 ${
                          isActive ? "text-cyan-400" : isDone ? "text-slate-400" : "text-slate-600"
                        }`}
                      >
                        <div className="mt-0.5">
                          {isDone ? (
                            <CheckCircle2 className="h-3 w-3 text-emerald-500 flex-shrink-0" />
                          ) : isActive ? (
                            <RefreshCw className="h-3 w-3 text-cyan-400 animate-spin flex-shrink-0" />
                          ) : (
                            <div className="h-3 w-3 rounded-full border border-slate-700 bg-slate-900 flex-shrink-0" />
                          )}
                        </div>
                        <span className="leading-tight">{step.label}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Section B: Spatial Reconstruction Datasets */}
          <div className="bg-slate-900/40 backdrop-blur-md rounded-xl p-5 border border-slate-800 flex flex-col gap-4">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
              <h2 className="text-sm font-semibold tracking-wide text-cyan-400 uppercase flex items-center gap-2">
                <FolderOpen className="h-4 w-4" /> Active Reconstructions
              </h2>
              <span className="text-[10px] font-mono text-slate-500">Firebase Storage</span>
            </div>

            <div className="flex flex-col gap-2">
              {presets.map((preset) => {
                const isActive = activeClipName === preset.name;
                return (
                  <button
                    key={preset.name}
                    onClick={() => {
                      if (!isProcessing) {
                        setActiveClipName(preset.name);
                        setCurrentTime(3.5);
                        setSelectedObjectId("obj-fpv-drone");
                        setCameraMode("follow");
                      }
                    }}
                    className={`text-left p-3 rounded-lg border transition duration-150 relative ${
                      isActive
                        ? "bg-slate-800/60 border-cyan-500/80 text-white shadow-md shadow-cyan-500/5 font-semibold"
                        : "bg-slate-950/20 border-slate-800/80 text-slate-400 hover:border-slate-700 hover:bg-slate-900/40"
                    }`}
                  >
                    <div className="text-xs truncate">{preset.name}</div>
                    <div className="flex items-center justify-between text-[10px] font-mono mt-1 text-slate-500">
                      <span>{preset.objects} Tracked Targets</span>
                      <span className="text-cyan-500/80 font-bold">{preset.points}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Middle Core: 3D Canvas WebGL Environment & Controls */}
        <div id="middle-canvas-viewport" className="xl:col-span-2 flex flex-col gap-6">
          <div className="relative flex-1 min-h-[500px] flex flex-col bg-slate-900/20 rounded-xl border border-slate-850 overflow-hidden">
            {/* Top Canvas Bar */}
            <div className="flex items-center justify-between bg-slate-950/60 p-4 border-b border-slate-900 z-10">
              <div className="flex items-center gap-2.5">
                <Compass className="h-4 w-4 text-cyan-400 animate-spin" />
                <div>
                  <h3 className="text-xs font-semibold text-white tracking-wide uppercase">
                    4D Point Cloud Depth Matrix Viewport
                  </h3>
                  <p className="text-[10px] text-slate-500 font-mono">
                    Scene: <span className="text-slate-300 font-bold">{activeClipName}</span>
                  </p>
                </div>
              </div>

              {/* Quick Display Switches */}
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-1.5 text-[11px] font-mono text-slate-400 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={showGhostPaths}
                    onChange={(e) => setShowGhostPaths(e.target.checked)}
                    className="rounded border-slate-800 text-cyan-500 bg-slate-950 focus:ring-0 w-3.5 h-3.5"
                  />
                  <span>Show Trajectories</span>
                </label>
              </div>
            </div>

            {/* THREE.JS WebGL Container */}
            <div className="flex-1 relative">
              <THREE_CANVAS_EXPORT
                currentTime={currentTime}
                trackedObjects={TRACKED_OBJECTS}
                selectedObjectId={selectedObjectId}
                onSelectObject={(id) => setSelectedObjectId(id)}
                cameraMode={cameraMode}
                pointConfidenceFilter={pointConfidenceFilter}
                showGhostPaths={showGhostPaths}
              />
            </div>

            {/* Float Canvas Tip overlay */}
            <div className="absolute bottom-4 left-4 z-10 bg-slate-950/90 border border-slate-800 px-3.5 py-2 rounded-lg pointer-events-none max-w-[280px]">
              <div className="flex items-start gap-2">
                <MousePointer className="h-4 w-4 text-cyan-400 mt-0.5" />
                <div>
                  <div className="text-[11px] font-semibold text-white uppercase tracking-wide">
                    Interactive Viewport hint
                  </div>
                  <div className="text-[10px] text-slate-400 leading-snug">
                    Left-click and drag to rotate the coordinate world. Scroll to zoom. Click directly on any moving target to lock tracking.
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Master Chronological Playback Board */}
          <div className="bg-slate-900/40 backdrop-blur-md rounded-xl p-5 border border-slate-800 flex flex-col gap-4">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
              <div className="flex items-center gap-2">
                <Monitor className="h-4 w-4 text-cyan-400" />
                <h4 className="text-xs font-semibold uppercase tracking-wide text-white">4D Telemetry Timeline Scrub</h4>
              </div>
              <div className="text-[11px] font-mono  text-slate-400 bg-slate-950 px-2 py-0.5 rounded border border-slate-850">
                FRAME: <span className="text-cyan-400 font-bold">{Math.floor(currentTime * 30).toString().padStart(3, "0")} / 360</span>
              </div>
            </div>

            <div className="flex flex-col gap-3">
              {/* Slider Scrub Bar */}
              <div className="relative group">
                <input
                  type="range"
                  min="0"
                  max={MAX_TIME}
                  step="0.05"
                  value={currentTime}
                  onChange={(e) => {
                    setCurrentTime(parseFloat(e.target.value));
                    setIsPlaying(false); // Pause on scrub
                  }}
                  className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-500 group-hover:bg-slate-700 transition"
                />
                
                {/* Visual Tick markers */}
                <div className="flex justify-between text-[9px] font-mono text-slate-600 px-1 mt-1.5 select-none">
                  <span>0.0s (IN)</span>
                  <span>2.0s</span>
                  <span>4.0s</span>
                  <span>6.0s (MID)</span>
                  <span>8.0s</span>
                  <span>10.0s</span>
                  <span>12.0s (OUT)</span>
                </div>
              </div>

              {/* Playback Buttons HUD */}
              <div className="flex flex-wrap items-center justify-between gap-4 mt-2">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setIsPlaying(!isPlaying)}
                    className={`px-4 py-2 rounded-lg font-semibold text-xs flex items-center gap-1.5 transition ${
                      isPlaying
                        ? "bg-purple-600 hover:bg-purple-700 text-white"
                        : "bg-cyan-500 hover:bg-cyan-600 text-slate-950 font-bold"
                    }`}
                  >
                    {isPlaying ? (
                      <>
                        <Pause className="h-3.5 w-3.5 fill-current" /> PAUSE METRIC
                      </>
                    ) : (
                      <>
                        <Play className="h-3.5 w-3.5 fill-current" /> PLAY LOOP
                      </>
                    )}
                  </button>

                  <div className="flex border border-slate-800 rounded-lg bg-slate-950/60 p-0.5">
                    {[0.5, 1.0, 2.0].map((speed) => (
                      <button
                        key={speed}
                        onClick={() => setPlaybackSpeed(speed)}
                        className={`px-2.5 py-1 text-[10px] font-mono rounded transition ${
                          playbackSpeed === speed
                            ? "bg-slate-800 text-cyan-400 font-bold"
                            : "text-slate-500 hover:text-slate-300"
                        }`}
                      >
                        {speed}x
                      </button>
                    ))}
                  </div>
                </div>

                {/* Instant Info reading */}
                <div className="text-[11px] font-mono text-slate-400 flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-cyan-400 animate-ping" />
                  <span>Time Synchronizer:</span>
                  <span className="text-white font-semibold">{currentTime.toFixed(2)}s</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right Hand: Multi-Agent Tracking Telemetry HUD */}
        <div id="right-sidebar" className="xl:col-span-1 flex flex-col gap-6">
          {/* Section A: Multi-Agent Impossible Camera Rig Setting */}
          <div className="bg-slate-900/40 backdrop-blur-md rounded-xl p-5 border border-slate-800 flex flex-col gap-4">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
              <h2 className="text-sm font-semibold tracking-wide text-cyan-400 uppercase flex items-center gap-2">
                <Compass className="h-4 w-4" /> Impossible Camera Rig
              </h2>
              <span className="text-[10px] font-mono text-slate-500">Coordinate Rig</span>
            </div>

            <p className="text-xs text-slate-400 leading-relaxed">
              Dynamically morph the 3D space. Mount the viewport camera straight onto the moving coordinate vector of any chosen agent.
            </p>

            <div className="grid grid-cols-3 gap-2">
              <button
                onClick={() => setCameraMode("free")}
                className={`py-2 px-1 text-center rounded-lg border flex flex-col items-center gap-1.5 transition ${
                  cameraMode === "free"
                    ? "bg-cyan-500/10 border-cyan-500 text-cyan-400 font-bold"
                    : "bg-slate-950/40 border-slate-850 text-slate-400 hover:border-slate-800 hover:bg-slate-900/20"
                }`}
              >
                <Compass className="h-4 w-4" />
                <span className="text-[10px] font-mono uppercase">Free Cam</span>
              </button>

              <button
                disabled={!selectedObjectId}
                onClick={() => setCameraMode("follow")}
                className={`py-2 px-1 text-center rounded-lg border flex flex-col items-center gap-1.5 transition ${
                  !selectedObjectId ? "opacity-40 cursor-not-allowed" : ""
                } ${
                  cameraMode === "follow"
                    ? "bg-purple-500/10 border-purple-500 text-purple-400 font-bold"
                    : "bg-slate-950/40 border-slate-850 text-slate-400 hover:border-slate-800 hover:bg-slate-900/20"
                }`}
              >
                <Layers3 className="h-4 w-4" />
                <span className="text-[10px] font-mono uppercase">Chase view</span>
              </button>

              <button
                disabled={!selectedObjectId}
                onClick={() => setCameraMode("fpv")}
                className={`py-2 px-1 text-center rounded-lg border flex flex-col items-center gap-1.5 transition ${
                  !selectedObjectId ? "opacity-40 cursor-not-allowed" : ""
                } ${
                  cameraMode === "fpv"
                    ? "bg-emerald-500/10 border-emerald-500 text-emerald-400 font-bold"
                    : "bg-slate-950/40 border-slate-850 text-slate-400 hover:border-slate-800 hover:bg-slate-900/20"
                }`}
              >
                <Video className="h-4 w-4" />
                <span className="text-[10px] font-mono uppercase">FPV Cockpit</span>
              </button>
            </div>
          </div>

          {/* Section B: Tracked Entities Board */}
          <div className="bg-slate-900/40 backdrop-blur-md rounded-xl p-5 border border-slate-800 flex flex-col gap-4">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
              <h2 className="text-sm font-semibold tracking-wide text-cyan-400 uppercase flex items-center gap-2">
                <Layers3 className="h-4 w-4" /> Reconstructed Agents
              </h2>
              <span className="text-[10px] font-mono text-slate-500">{TRACKED_OBJECTS.length} Active</span>
            </div>

            <div className="flex flex-col gap-2.5">
              {TRACKED_OBJECTS.map((obj) => {
                const isSelected = obj.id === selectedObjectId;
                const posNow = obj.getPosition(currentTime);

                return (
                  <button
                    key={obj.id}
                    onClick={() => {
                      setSelectedObjectId(obj.id);
                      if (cameraMode === "free") {
                        setCameraMode("follow"); // snap to tracking lookAt
                      }
                    }}
                    className={`text-left p-3 rounded-lg border transition duration-150 flex flex-col gap-2 ${
                      isSelected
                        ? "bg-slate-800/80 border-cyan-500 text-white"
                        : "bg-slate-950/30 border-slate-850/80 text-slate-400 hover:border-slate-800 hover:bg-slate-900/30"
                    }`}
                  >
                    <div className="flex items-center justify-between w-full">
                      <div className="flex items-center gap-2">
                        <span
                          className="h-2 w-2 rounded-full"
                          style={{ backgroundColor: obj.color }}
                        />
                        <span className="text-xs font-semibold tracking-wide">{obj.name}</span>
                      </div>
                      <span className="text-[9px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-950 border border-slate-850">
                        {obj.category}
                      </span>
                    </div>

                    {/* Small live dynamic coordinates ticker */}
                    <div className="grid grid-cols-3 text-[10px] font-mono text-slate-500 bg-slate-950/60 p-1.5 rounded divide-x divide-slate-900 text-center">
                      <div>
                        X <span className="text-slate-300 ml-0.5">{posNow.x.toFixed(1)}</span>
                      </div>
                      <div>
                        Y <span className="text-slate-300 ml-0.5">{posNow.y.toFixed(1)}</span>
                      </div>
                      <div>
                        Z <span className="text-slate-300 ml-0.5">{posNow.z.toFixed(1)}</span>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Section C: Live Selected Telemetry Readout */}
          {selectedObject && (
            <div className="bg-slate-900/40 backdrop-blur-md rounded-xl p-5 border border-slate-800 flex flex-col gap-4">
              <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
                <h2 className="text-sm font-semibold tracking-wide text-cyan-400 uppercase flex items-center gap-2">
                  <Activity className="h-4 w-4 text-purple-400 animate-pulse" /> Live Telemetry Matrix
                </h2>
                <span className="text-[10px] font-mono text-cyan-400 font-bold uppercase">Lock tracking</span>
              </div>

              <div className="flex flex-col gap-3 font-mono text-xs">
                <div className="flex justify-between items-center bg-slate-950/60 py-2 px-3 rounded border border-slate-900">
                  <span className="text-slate-500 uppercase tracking-tight text-[10px]">Target Identifier:</span>
                  <span className="text-white font-medium truncate max-w-[140px]">{selectedObject.name}</span>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div className="bg-slate-950/60 p-2.5 rounded border border-slate-900 text-center">
                    <span className="text-slate-500 text-[9px] uppercase block mb-1">Interpolated Speed</span>
                    <span className="text-sm font-bold text-cyan-400">
                      {(selectedObject.baseSpeed + Math.sin(currentTime * 0.8) * 3).toFixed(1)} km/h
                    </span>
                  </div>
                  <div className="bg-slate-950/60 p-2.5 rounded border border-slate-900 text-center">
                    <span className="text-slate-500 text-[9px] uppercase block mb-1">GCP Flow Confidence</span>
                    <span className="text-sm font-bold text-emerald-400">
                      {(98.4 + Math.sin(currentTime) * 0.4).toFixed(2)}%
                    </span>
                  </div>
                </div>

                <div className="bg-slate-950/60 p-3 rounded border border-slate-900 flex flex-col gap-2 text-[11px]">
                  <div className="flex justify-between">
                    <span className="text-slate-500 text-[10px]">X COORDINATE:</span>
                    <span className="text-white">{objectPos.x.toFixed(4)} m</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500 text-[10px]">Y ELEVATION:</span>
                    <span className="text-white">{objectPos.y.toFixed(4)} m</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500 text-[10px]">Z DEPTH PATH:</span>
                    <span className="text-white">{objectPos.z.toFixed(4)} m</span>
                  </div>
                  <div className="flex justify-between border-t border-slate-900 pt-1.5 mt-0.5">
                    <span className="text-slate-500 text-[10px]">VECTOR HEADING:</span>
                    <span className="text-purple-400 font-bold">{objectHeadingDeg.toFixed(1)}° (Tangent)</span>
                  </div>
                </div>

                {/* Trajectory Extraction Action Links */}
                <button
                  onClick={() => {
                    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(selectedObject));
                    const downloadAnchorNode = document.createElement("a");
                    downloadAnchorNode.setAttribute("href", dataStr);
                    downloadAnchorNode.setAttribute("download", `trajectory_${selectedObject.id}.json`);
                    document.body.appendChild(downloadAnchorNode);
                    downloadAnchorNode.click();
                    downloadAnchorNode.remove();
                  }}
                  className="w-full bg-slate-800 hover:bg-slate-700 hover:text-white transition py-2 px-3 rounded text-[11px] font-mono flex items-center justify-center gap-1 text-slate-300 font-semibold"
                >
                  <Download className="h-3.5 w-3.5 text-cyan-400" /> Export Trajectory JSON
                </button>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* 3. Immersive Matrix Sub-Footer Status Line */}
      <footer id="network-bar" className="bg-slate-950 border-t border-slate-900/90 py-3.5 px-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs font-mono text-slate-500">
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-emerald-500 shadow-md shadow-emerald-500/50" />
          <span>RECONSTRUCTIVE FLOW SYSTEM BROADCASTING LIVE FRAME BUFFERS</span>
        </div>
        <div className="flex items-center gap-4">
          <span>PIPELINE PRECOMPILE: <span className="text-cyan-400">SUCCESS</span></span>
          <span>4RC POINT CHANNELS: <span className="text-white">TRUE_FLOW_FIELDS</span></span>
        </div>
      </footer>
    </div>
  );
}
