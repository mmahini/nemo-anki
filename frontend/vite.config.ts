import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backendUrl = env.VITE_BACKEND_URL ?? "http://backend:8000";

  return {
    plugins: [
      react(),
      VitePWA({
        // "prompt": a detected update waits for the user — the UpdateToast
        // shows "new version available" with an update button — instead of
        // yanking the page out from under them mid-review.
        registerType: "prompt",
        // We register the service worker ourselves (src/pwa.ts) so we can also
        // poll for updates while the app stays open — installed PWAs (desktop/
        // Android) are often left running for a long time, and a plain SW only
        // checks for updates on navigation.
        injectRegister: null,
        // vite-plugin-pwa doesn't run the service worker under `vite dev` by
        // default — without this, navigator.serviceWorker.ready (src/pwa.ts,
        // src/push.ts, src/lib/pushNotifications.ts) never resolves, so any
        // push opt-in hangs forever in local dev.
        devOptions: { enabled: true, type: "module" },
        includeAssets: ["cards.svg", "favicon.ico", "apple-touch-icon-180x180.png"],
        manifest: {
          name: "Nemo Anki",
          short_name: "Nemo Anki",
          description: "Spaced-repetition flashcards for German and English.",
          theme_color: "#4c6ef5",
          background_color: "#f6f7fb",
          display: "standalone",
          // Installed app opens straight into the app, not the marketing
          // landing (LandingPage also redirects when running standalone, for
          // installs that predate this manifest).
          start_url: "/app",
          icons: [
            { src: "pwa-64x64.png", sizes: "64x64", type: "image/png" },
            { src: "pwa-192x192.png", sizes: "192x192", type: "image/png" },
            { src: "pwa-512x512.png", sizes: "512x512", type: "image/png" },
            {
              src: "maskable-icon-512x512.png",
              sizes: "512x512",
              type: "image/png",
              purpose: "maskable",
            },
          ],
        },
        workbox: {
          navigateFallbackDenylist: [/^\/api\//, /^\/media\//],
          // Adds push/notificationclick handlers to the generated SW without
          // switching off generateSW mode (see public/push-sw.js).
          importScripts: ["push-sw.js"],
          runtimeCaching: [
            {
              urlPattern: ({ url }) => url.pathname.startsWith("/api/"),
              handler: "NetworkFirst",
              options: {
                cacheName: "api-cache",
                networkTimeoutSeconds: 5,
                cacheableResponse: { statuses: [0, 200] },
              },
            },
            {
              urlPattern: ({ url }) => url.pathname.startsWith("/media/"),
              handler: "CacheFirst",
              options: {
                cacheName: "media-cache",
                expiration: { maxEntries: 200, maxAgeSeconds: 30 * 24 * 60 * 60 },
                cacheableResponse: { statuses: [0, 200] },
              },
            },
          ],
        },
      }),
    ],
    server: {
      host: "0.0.0.0",
      port: 5173,
      watch: { usePolling: true },
      proxy: {
        "/api": {
          target: backendUrl,
          changeOrigin: true,
        },
        "/media": {
          target: backendUrl,
          changeOrigin: true,
        },
      },
    },
    preview: {
      host: "0.0.0.0",
      port: 5173,
      proxy: {
        "/api": {
          target: backendUrl,
          changeOrigin: true,
        },
        "/media": {
          target: backendUrl,
          changeOrigin: true,
        },
      },
    },
  };
});
