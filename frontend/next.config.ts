import type { NextConfig } from "next";

const config: NextConfig = {
  devIndicators: false,
  distDir: process.env.ARIANA_NEXT_BUILD_DIR || ".next",
};

export default config;
