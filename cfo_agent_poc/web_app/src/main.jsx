import React from "react";
import { createRoot } from "react-dom/client";
import "../styles.css";
import "../vendor/gsap.min.js";
import "../vendor/ScrollTrigger.min.js";
import App, { CRITICAL_IMAGE_URLS } from "./App.jsx";

document.body.classList.add("app-loading");

function preloadImage(src) {
  return new Promise((resolve) => {
    if (!src) {
      resolve();
      return;
    }
    const image = new Image();
    image.onload = async () => {
      try {
        await image.decode?.();
      } catch (_) {
        /* Image is already loaded; decode support varies. */
      }
      resolve();
    };
    image.onerror = () => resolve();
    image.src = src;
  });
}

window.cfoStaticReady = Promise.all(CRITICAL_IMAGE_URLS.map(preloadImage));

createRoot(document.getElementById("root")).render(<App />);

requestAnimationFrame(async () => {
  await import("./motion.js");
  await import("./legacy-controller.js");
});
