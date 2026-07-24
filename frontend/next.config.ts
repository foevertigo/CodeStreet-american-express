import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Turbopack is the default in Next.js 16 — no webpack config needed.
  // The Silero VAD ONNX model and worklet are served from /public/ directly.
  turbopack: {},
};

export default nextConfig;
