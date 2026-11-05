import Lenis from "lenis";

/**
 * 页面上下滚动的平滑（Lenis，只接管滚轮，触屏保持原生）。
 * - 反向滚轮时丢掉上一方向还没走完的行程，从当前位置起步，不会出现“反向那一格被抵消掉”的挤压感。
 * - LERP 每帧追上剩余距离的比例：越大越跟手、停得越快；默认 0.1 尾巴约 1 秒，拖拽感偏重。
 * - 对话记录、弹窗正文、横向胶囊轨道这些内层滚动区：allowNestedScroll 让它们照常原生滚动，滚到头才交还给页面。
 * - 弹窗 / 展开对话时 body 已经锁了滚动，这里跟着 stop()，免得滚轮在背后推动页面。
 * - prefers-reduced-motion 下不启用。
 * 不引入 lenis.css：它会在 stop() 时给 html 加 overflow: clip，和 body 上现有的锁滚动、滚动条补偿冲突。
 */
const LERP = 0.24;
const LOCK_CLASSES = ["modal-open", "chat-expanded-open"];

export function startSmoothScroll() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return null;

  const lenis = new Lenis({
    anchors: true,
    allowNestedScroll: true,
    autoRaf: true,
    lerp: LERP,
    virtualScroll: ({ deltaY }) => {
      const pending = lenis.targetScroll - lenis.animatedScroll;
      if (deltaY && pending && Math.sign(deltaY) !== Math.sign(pending)) {
        lenis.targetScroll = lenis.animatedScroll;
      }
    },
  });
  const syncLock = () => {
    const locked = LOCK_CLASSES.some((name) => document.body.classList.contains(name));
    if (locked) lenis.stop();
    else lenis.start();
  };
  new MutationObserver(syncLock).observe(document.body, { attributes: true, attributeFilter: ["class"] });
  syncLock();
  return lenis;
}
