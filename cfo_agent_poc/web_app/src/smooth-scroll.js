import Lenis from "lenis";

/**
 * 页面上下滚动的惯性平滑（Lenis，手感对齐 cuelume-site：默认 lerp 0.1，只接管滚轮，触屏保持原生）。
 * - 对话记录、弹窗正文、横向胶囊轨道这些内层滚动区：allowNestedScroll 让它们照常原生滚动，滚到头才交还给页面。
 * - 弹窗 / 展开对话时 body 已经锁了滚动，这里跟着 stop()，免得滚轮在背后推动页面。
 * - prefers-reduced-motion 下不启用。
 * 不引入 lenis.css：它会在 stop() 时给 html 加 overflow: clip，和 body 上现有的锁滚动、滚动条补偿冲突。
 */
const LOCK_CLASSES = ["modal-open", "chat-expanded-open"];

export function startSmoothScroll() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return null;

  const lenis = new Lenis({ anchors: true, allowNestedScroll: true, autoRaf: true });
  const syncLock = () => {
    const locked = LOCK_CLASSES.some((name) => document.body.classList.contains(name));
    if (locked) lenis.stop();
    else lenis.start();
  };
  new MutationObserver(syncLock).observe(document.body, { attributes: true, attributeFilter: ["class"] });
  syncLock();
  return lenis;
}
