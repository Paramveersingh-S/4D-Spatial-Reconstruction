/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

export interface TrackedObject {
  id: string;
  name: string;
  category: "drone" | "vehicle" | "pedestrian" | "infrastructure";
  color: string;
  baseSpeed: number; // in km/h
  // Function to generate coordinates based on local timeline time (t)
  getPosition: (t: number) => { x: number; y: number; z: number };
  getHeading: (t: number) => number; // in radians
}

export interface PointCloudParticle {
  id: number;
  x: number;
  y: number;
  z: number;
  color: string;
  size: number;
  // Dynamic offset logic through time
  displacement?: (t: number) => { dx: number; dy: number; dz: number };
}

export type ConnectionStatus = "CONNECTED" | "DISCONNECTED" | "CONNECTING";

export interface ProcessingStep {
  id: string;
  label: string;
  duration: number; // simulated seconds
  status: "pending" | "processing" | "completed";
}
