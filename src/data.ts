/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { TrackedObject, PointCloudParticle, ProcessingStep } from "./types";

// Dynamic Math-Based Tracked Objects
export const TRACKED_OBJECTS: TrackedObject[] = [
  {
    id: "obj-fpv-drone",
    name: "Quadcopter FPV-9",
    category: "drone",
    color: "#06b6d4", // Cyan
    baseSpeed: 48,
    getPosition: (t: number) => {
      // Loop or curve: circular orbit with sine height change
      const radius = 18;
      const speedMultiplier = 0.5;
      const angle = t * speedMultiplier + 0.5;
      return {
        x: Math.cos(angle) * radius,
        y: 10 + Math.sin(t * 1.2) * 3,
        z: Math.sin(angle) * radius,
      };
    },
    getHeading: (t: number) => {
      const speedMultiplier = 0.5;
      const angle = t * speedMultiplier + 0.5;
      // Heading should be tangent to the circle
      return angle + Math.PI / 2;
    },
  },
  {
    id: "obj-sedan-x7",
    name: "Autonomous Vehicle Sedan-X7",
    category: "vehicle",
    color: "#a855f7", // Purple
    baseSpeed: 60,
    getPosition: (t: number) => {
      // Moves along a highway road bed (e.g. constant X, shifting Z)
      const startZ = -30;
      const speed = 5.2; // units per second
      return {
        x: -4,
        y: 1.1, // slightly hovered off ground
        z: startZ + t * speed,
      };
    },
    getHeading: (t: number) => {
      return 0; // facing straight along +Z
    },
  },
  {
    id: "obj-ebike-3",
    name: "Commuter E-Bike #03",
    category: "vehicle",
    color: "#10b981", // Emerald
    baseSpeed: 25,
    getPosition: (t: number) => {
      // Moves slower on the opposite side sidewalk (+X)
      const startZ = 25;
      const speed = -2.1;
      return {
        x: 6.5,
        y: 0.8,
        z: startZ + t * speed,
      };
    },
    getHeading: (t: number) => {
      return Math.PI; // facing opposite (-Z)
    },
  },
  {
    id: "obj-pedestrian-alpha",
    name: "Pedestrian (Conditional Query #4)",
    category: "pedestrian",
    color: "#f59e0b", // Amber
    baseSpeed: 5,
    getPosition: (t: number) => {
      // Walking in a small path across the crosswalk at Z = 5
      const startX = -8;
      const speed = 0.8;
      return {
        x: Math.min(startX + t * speed, 8),
        y: 0.7,
        z: 4.5,
      };
    },
    getHeading: (t: number) => {
      return Math.PI / 2; // facing +X
    },
  }
];

// Reconstructed Static Environment Points (representing buildings, ground, lanes, street lamps)
export function generateEnvironmentPoints(): PointCloudParticle[] {
  const points: PointCloudParticle[] = [];
  let idAcc = 0;

  // 1. Ground/Road Points (-35 to +35 in Z, -15 to +15 in X)
  for (let x = -15; x <= 15; x += 1.5) {
    for (let z = -35; z <= 35; z += 1.5) {
      const isRoad = Math.abs(x) < 5;
      const isSidewalk = Math.abs(x) >= 5 && Math.abs(x) < 9;
      
      let color = "#374151"; // dark gray road
      let y = 0;
      
      if (isSidewalk) {
        color = "#4b5563"; // medium gray sidewalk
        y = 0.1;
      } else if (!isRoad) {
        color = "#1f2937"; // dark landscape
        y = -0.1;
      } else {
        // Add road stripes (white indicators)
        if (Math.abs(x) < 0.2 && Math.floor(z) % 6 === 0) {
          color = "#e5e7eb";
        }
      }

      // Add a tiny bit of high-tech spatial noise
      points.push({
        id: idAcc++,
        x: x + (Math.random() - 0.5) * 0.3,
        y: y + (Math.random() - 0.5) * 0.05,
        z: z + (Math.random() - 0.5) * 0.3,
        color,
        size: Math.random() * 0.05 + 0.03,
      });
    }
  }

  // 2. Twin Buildings/Structures (left side of road X = -12, right side X = 12)
  const sides = [-12, 12];
  sides.forEach((sideX) => {
    // Generate heights of points to create a grid building facade
    for (let z = -30; z <= 30; z += 3) {
      const buildingHeight = 12 + Math.sin(z) * 4; // varying heights
      for (let y = 0.5; y <= buildingHeight; y += 1.2) {
        for (let offset = -2; offset <= 2; offset += 1.0) {
          points.push({
            id: idAcc++,
            x: sideX + offset + (Math.random() - 0.5) * 0.2,
            y: y + (Math.random() - 0.5) * 0.1,
            z: z + (Math.random() - 0.5) * 0.2,
            color: sideX < 0 ? "#1e293b" : "#111827", // futuristic tint
            size: Math.random() * 0.06 + 0.04,
          });
        }
      }
    }
  });

  // 3. Floating Reconstructed Cloud Overhead (Air Density flow fields)
  for (let i = 0; i < 300; i++) {
    const rx = (Math.random() - 0.5) * 40;
    const ry = 8 + Math.random() * 10;
    const rz = (Math.random() - 0.5) * 60;
    points.push({
      id: idAcc++,
      x: rx,
      y: ry,
      z: rz,
      // Using standard hex since Three.js Color parsing doesn't natively accept rgba strings with alpha in this context.
      color: "#06b6d4", // transparent cyan visual flow
      size: Math.random() * 0.04 + 0.02,
    });
  }

  return points;
}

// Simulated Pipeline Logging Steps
export const PROCESS_STEPS_TEMPLATE: ProcessingStep[] = [
  { id: "1", label: "Hashing signature and uploading MP4 source file...", duration: 1.5, status: "pending" },
  { id: "2", label: "Computing Optical Flow Fields using RAFT", duration: 2.0, status: "pending" },
  { id: "3", label: "Executing 4RC Conditional Querying over keyframe trajectories...", duration: 2.5, status: "pending" },
  { id: "4", label: "Compiling point-cloud density maps & depth triangulation...", duration: 2.0, status: "pending" },
  { id: "5", label: "Generating camera paths and pushing metadata JSON to Firestore...", duration: 1.5, status: "pending" },
];
