/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { TrackedObject, PointCloudParticle } from "../types";
import { generateEnvironmentPoints } from "../data";

interface ThreeCanvasProps {
  currentTime: number;
  trackedObjects: TrackedObject[];
  selectedObjectId: string | null;
  onSelectObject: (id: string | null) => void;
  cameraMode: "free" | "follow" | "fpv";
  pointConfidenceFilter: number; // 0 to 100
  showGhostPaths: boolean;
}

export default function ThreeCanvas({
  currentTime,
  trackedObjects,
  selectedObjectId,
  onSelectObject,
  cameraMode,
  pointConfidenceFilter,
  showGhostPaths,
}: ThreeCanvasProps) {
  const mountRef = useRef<HTMLDivElement>(null);
  const stateRef = useRef({ currentTime, selectedObjectId, cameraMode, showGhostPaths, onSelectObject });

  // Update references to prevent dirty closures in the render tick
  useEffect(() => {
    stateRef.current = { currentTime, selectedObjectId, cameraMode, showGhostPaths, onSelectObject };
  }, [currentTime, selectedObjectId, cameraMode, showGhostPaths, onSelectObject]);

  useEffect(() => {
    if (!mountRef.current) return;

    const width = mountRef.current.clientWidth || 800;
    const height = mountRef.current.clientHeight || 500;

    // 1. Scene setup
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#030712"); // deep slate-950
    scene.fog = new THREE.FogExp2("#030712", 0.015);

    // 2. Camera setup
    const camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 1000);
    // Initial standard position
    camera.position.set(0, 20, 45);

    // 3. WebGL Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mountRef.current.appendChild(renderer.domElement);

    // 3.5 Post-Processing (Neon Cinematic Bloom)
    const renderScene = new RenderPass(scene, camera);
    const bloomPass = new UnrealBloomPass(new THREE.Vector2(width, height), 1.5, 0.4, 0.85);
    bloomPass.threshold = 0.15;
    bloomPass.strength = 1.6; // High intensity for that futuristic glow
    bloomPass.radius = 0.8;

    const composer = new EffectComposer(renderer);
    composer.addPass(renderScene);
    composer.addPass(bloomPass);

    // 4. Orbit Controls (Only fully engaged in Free Cam mode)
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.maxPolarAngle = Math.PI / 2 - 0.02; // restrict looking below ground
    controls.minDistance = 2;
    controls.maxDistance = 150;

    // 5. Lights
    const ambientLight = new THREE.AmbientLight("#475569", 1.8);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight("#06b6d4", 2.5);
    dirLight.position.set(20, 40, 20);
    scene.add(dirLight);

    const dirLight2 = new THREE.DirectionalLight("#a855f7", 1.5);
    dirLight2.position.set(-20, 30, -20);
    scene.add(dirLight2);

    // 6. Floor Grid / Coordinate Reference
    const gridHelper = new THREE.GridHelper(80, 40, "#111827", "#1f2937");
    gridHelper.position.y = 0;
    scene.add(gridHelper);

    // 7. Generate Spatial Point Cloud
    const envPoints = generateEnvironmentPoints();
    const particleCount = envPoints.length;

    const positions = new Float32Array(particleCount * 3);
    const colors = new Float32Array(particleCount * 3);
    const sizes = new Float32Array(particleCount);

    const tempColor = new THREE.Color();
    envPoints.forEach((pt, i) => {
      positions[i * 3] = pt.x;
      positions[i * 3 + 1] = pt.y;
      positions[i * 3 + 2] = pt.z;

      tempColor.set(pt.color || "#4b5563");
      colors[i * 3] = tempColor.r;
      colors[i * 3 + 1] = tempColor.g;
      colors[i * 3 + 2] = tempColor.b;

      sizes[i] = pt.size * (Math.random() * 1.5 + 0.5);
    });

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    geometry.setAttribute("size", new THREE.BufferAttribute(sizes, 1));

    // Custom point texture with rounded glowing circular dots
    const canvas = document.createElement("canvas");
    canvas.width = 16;
    canvas.height = 16;
    const ctx = canvas.getContext("2d");
    if (ctx) {
      const grad = ctx.createRadialGradient(8, 8, 0, 8, 8, 8);
      grad.addColorStop(0, "rgba(255, 255, 255, 1)");
      grad.addColorStop(0.5, "rgba(255, 255, 255, 0.5)");
      grad.addColorStop(1, "rgba(255, 255, 255, 0)");
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, 16, 16);
    }
    const texture = new THREE.CanvasTexture(canvas);

    const pointsMaterial = new THREE.PointsMaterial({
      size: 0.35,
      map: texture,
      vertexColors: true,
      transparent: true,
      opacity: 0.75,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });

    const pointCloudSystem = new THREE.Points(geometry, pointsMaterial);
    scene.add(pointCloudSystem);

    // 8. Tracked Objects Visual representations
    const objectMeshes: Map<
      string,
      {
        group: THREE.Group;
        wireframeBox: THREE.Mesh;
        trailLine: THREE.Line;
        trailGeometry: THREE.BufferGeometry;
        trailPoints: THREE.Vector3[];
      }
    > = new Map();

    trackedObjects.forEach((obj) => {
      const objGroup = new THREE.Group();

      // Main interactive neon capsule / sphere representation
      const coreGeom = new THREE.BoxGeometry(1.6, 1.0, 2.5);
      const wireframeMaterial = new THREE.MeshBasicMaterial({
        color: new THREE.Color(obj.color),
        wireframe: true,
        transparent: true,
        opacity: 0.8,
      });
      const wireframeBox = new THREE.Mesh(coreGeom, wireframeMaterial);
      objGroup.add(wireframeBox);

      // Add a glowing central point
      const glowGeom = new THREE.SphereGeometry(0.35, 8, 8);
      const glowMaterial = new THREE.MeshBasicMaterial({
        color: new THREE.Color(obj.color),
      });
      const glowMesh = new THREE.SphereGeometry(0.2, 8, 8);
      objGroup.add(new THREE.Mesh(glowMesh, glowMaterial));

      // Pointer direction indicator cone
      const pointerGeom = new THREE.ConeGeometry(0.25, 0.75, 4);
      pointerGeom.rotateX(Math.PI / 2); // align forward along Z axis
      const pointerMesh = new THREE.Mesh(
        pointerGeom,
        new THREE.MeshBasicMaterial({ color: obj.color })
      );
      pointerMesh.position.set(0, 0, 1.4);
      objGroup.add(pointerMesh);

      // Assign user data payload for custom clicking/raycasting
      wireframeBox.userData = { id: obj.id };

      scene.add(objGroup);

      // Trajectory Trail Lines (Rendered continuously)
      const MAX_TRAIL_LEN = 120;
      const trailPoints: THREE.Vector3[] = [];
      // Populate historical points to represent reconstructed trajectory path
      for (let i = 0; i <= MAX_TRAIL_LEN; i++) {
        const simTime = (i / MAX_TRAIL_LEN) * 12.0;
        const pos = obj.getPosition(simTime);
        trailPoints.push(new THREE.Vector3(pos.x, pos.y, pos.z));
      }

      const trailGeometry = new THREE.BufferGeometry().setFromPoints(trailPoints);
      const trailMaterial = new THREE.LineBasicMaterial({
        color: new THREE.Color(obj.color),
        transparent: true,
        opacity: 0.6,
        linewidth: 2, // will be ignored by many platforms to fallback, but looks clean
      });
      const trailLine = new THREE.Line(trailGeometry, trailMaterial);
      scene.add(trailLine);

      objectMeshes.set(obj.id, {
        group: objGroup,
        wireframeBox,
        trailLine,
        trailGeometry,
        trailPoints,
      });
    });

    // Raycast handling for selecting moving objects in 3D canvas
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    const onCanvasClick = (event: MouseEvent) => {
      // Get click position relative to canvas wrapper bounding rect
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(mouse, camera);

      // List collidable wireframe boxes
      const targetsToIntersect: THREE.Object3D[] = [];
      objectMeshes.forEach((meshData) => {
        targetsToIntersect.push(meshData.wireframeBox);
      });

      const intersects = raycaster.intersectObjects(targetsToIntersect);
      if (intersects.length > 0) {
        const hitId = intersects[0].object.userData.id;
        if (hitId) {
          stateRef.current.onSelectObject(hitId);
        }
      } else {
        // Did not hit anything, do not automatically deselect so we maintain focus
      }
    };

    renderer.domElement.addEventListener("click", onCanvasClick);

    // 9. Interactive Particle Simulation Loop
    let animationFrameId: number;
    let startTime = performance.now();

    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);

      const elapsed = (performance.now() - startTime) / 1000;
      const currentSimTime = stateRef.current.currentTime;
      const currentSelected = stateRef.current.selectedObjectId;
      const currentMode = stateRef.current.cameraMode;
      const currentShowGhost = stateRef.current.showGhostPaths;

      // Slightly animate the scale and noise of static point cloud system to show "live spatial confidence streams"
      const ptsAttr = pointCloudSystem.geometry.attributes.position as THREE.BufferAttribute;
      const pointsArray = ptsAttr.array as Float32Array;

      // Pulse a minor shift
      for (let i = 0; i < particleCount; i++) {
        // Check confidence levels
        if (i % 7 === 0) {
          // Pulse vertical height slightly in flow coordinates
          const origY = envPoints[i].y;
          pointsArray[i * 3 + 1] = origY + Math.sin(elapsed * 2 + i) * 0.08;
        }
      }
      ptsAttr.needsUpdate = true;

      // Update positions of tracked meshes based on simulation time
      let targetCameraLookAt = new THREE.Vector3(0, 5, 0);
      let targetCameraPos: THREE.Vector3 | null = null;
      let targetForward = new THREE.Vector3(0, 0, 1);

      trackedObjects.forEach((obj) => {
        const meshData = objectMeshes.get(obj.id);
        if (!meshData) return;

        // Fetch spatial positions mapped directly to simulation time (0s-12s)
        const pos = obj.getPosition(currentSimTime);
        meshData.group.position.set(pos.x, pos.y, pos.z);

        // Calculate heading to rotate object correctly
        const heading = obj.getHeading(currentSimTime);
        meshData.group.rotation.y = heading;

        // Toggle trails ghost visibility
        meshData.trailLine.visible = currentShowGhost;

        // Glow highlighting selected target
        const isSelected = obj.id === currentSelected;
        const mat = meshData.wireframeBox.material as THREE.MeshBasicMaterial;
        mat.color.set(isSelected ? "#ff007f" : obj.color); // glowing pink selection HUD
        mat.opacity = isSelected ? 0.95 : 0.55;

        // Is this the selected object tracking target?
        if (isSelected) {
          targetCameraLookAt.set(pos.x, pos.y, pos.z);
          
          // Get direction vector based on heading rotation
          const dirX = Math.sin(heading);
          const dirZ = Math.cos(heading);
          targetForward.set(dirX, 0, dirZ).normalize();

          if (currentMode === "follow") {
            // Camera tracks trailing behind the object looking at it
            targetCameraPos = new THREE.Vector3(
              pos.x - dirX * 12,
              pos.y + 6,
              pos.z - dirZ * 12
            );
          } else if (currentMode === "fpv") {
            // First Person Visual perspective from inside the front sensor rig
            targetCameraPos = new THREE.Vector3(
              pos.x + dirX * 1.5,
              pos.y + 0.6,
              pos.z + dirZ * 1.5
            );
            // Look forward towards trajectory travel path
            targetCameraLookAt.addVectors(targetCameraPos, targetForward.multiplyScalar(15));
          }
        }
      });

      // 10. Implement Dynamic Camera Rig interpolation
      if (currentSelected && (currentMode === "follow" || currentMode === "fpv") && targetCameraPos) {
        controls.enabled = false; // Disable controls so it tracks smoothly
        
        // Fast geometric interpolation lerp
        camera.position.lerp(targetCameraPos, 0.08);
        controls.target.lerp(targetCameraLookAt, 0.1);
      } else {
        // Normal orbit camera
        controls.enabled = true;
      }

      controls.update();
      // Replace standard renderer with the glowing post-processing composer
      composer.render();
    };

    animate();

    // 11. Handle Resizing of window
    const handleResize = () => {
      if (!mountRef.current) return;
      const w = mountRef.current.clientWidth;
      const h = mountRef.current.clientHeight;

      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
      composer.setSize(w, h);
    };

    window.addEventListener("resize", handleResize);

    // Cleanups
    return () => {
      if (mountRef.current && renderer.domElement) {
        mountRef.current.removeChild(renderer.domElement);
      }
      renderer.dispose();
      window.removeEventListener("resize", handleResize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []); // Run only once on mount. Use stateRef to access dynamic values safely.

  return (
    <div
      id="3d-canvas-viewport"
      ref={mountRef}
      className="w-full h-full relative cursor-crosshair rounded-xl overflow-hidden border border-slate-800 bg-[#030712] shadow-2xl"
    >
      <div className="absolute top-4 right-4 z-10 bg-slate-900/80 backdrop-blur-md px-3 py-1.5 rounded-md border border-slate-700 pointer-events-none text-right">
        <div className="text-[10px] uppercase tracking-wider text-cyan-400 font-mono font-semibold">WebGL Active</div>
        <div className="text-xs text-slate-300 font-mono">
          Camera Mode: <span className="text-white uppercase font-bold">{cameraMode}</span>
        </div>
      </div>
    </div>
  );
}
