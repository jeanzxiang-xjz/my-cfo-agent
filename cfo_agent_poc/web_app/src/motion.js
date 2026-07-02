(function () {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let initialized = false;
  let dynamicAnimationCount = 0;

  function $(selector, root = document) {
    return root.querySelector(selector);
  }

  function $$(selector, root = document) {
    return Array.from(root.querySelectorAll(selector));
  }

  function hasGsap() {
    return Boolean(window.gsap && window.ScrollTrigger);
  }

  async function waitForStaticReady() {
    try {
      await window.cfoStaticReady;
    } catch (_) {
      /* Static preload failures should not block the app. */
    }
  }

  async function waitForDataReady() {
    try {
      await window.cfoDataReady;
    } catch (_) {
      /* The controller owns data error rendering. Motion should not deadlock. */
    }
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => {
      const map = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      };
      return map[char];
    });
  }

  function wrapTitleMask(element) {
    if (!element || element.dataset.motionWrapped) return;
    const text = element.textContent;
    element.innerHTML = `<span class="motion-title-mask"><span>${escapeHtml(text)}</span></span>`;
    element.dataset.motionWrapped = "true";
  }

  function markMotionTargets() {
    $$(".neural-panel, .command-console, .ledger-panel, .metric-matrix > div, .decision-item, .category-row, .transaction-item").forEach((node) => {
      node.classList.add("motion-card");
    });
    $$(".panel-heading h2, .ledger-heading h2, .modal-header h2").forEach(wrapTitleMask);
    wrapTitleMask($(".agent-hero h1"));
  }

  function openingAnimation() {
    const gsap = window.gsap;
    const overlay = $(".opening-overlay");
    const heroTitle = $(".agent-hero h1 .motion-title-mask > span");
    const headerSummary = $("#headerSummary");
    const commandRail = $(".command-rail");
    const periodControl = $(".period-control");
    const openingIllustration = $(".opening-illustration-wrap");
    const openingIllustrationImage = $(".opening-illustration");
    const agentHero = $(".agent-hero");
    const agentVisual = $(".agent-visual");
    const agentPortrait = $(".agent-portrait");
    const firstCards = [
      ...$$(".agent-hero .message"),
      ...$$(".agent-hero .quick-prompts button"),
      $(".agent-hero .chat-form"),
      ...$$(".agent-visual-card"),
    ];

    document.body.classList.remove("app-loading");
    document.body.classList.add("motion-running", "motion-ready");
    document.body.classList.remove("motion-complete");
    gsap.set(overlay, { autoAlpha: 1, clipPath: "inset(0% 0% 0% 0%)" });
    gsap.set(commandRail, { y: -34, autoAlpha: 0 });
    gsap.set(heroTitle, { yPercent: 118, scaleX: 0.82, skewY: 2, transformOrigin: "left center" });
    gsap.set(headerSummary, { y: 26, autoAlpha: 0 });
    gsap.set(periodControl, { y: 24, autoAlpha: 0 });
    gsap.set(openingIllustration, { x: 46, autoAlpha: 0, clipPath: "inset(0% 0% 100% 0%)" });
    gsap.set(openingIllustrationImage, { scale: 1.06, y: 18, transformOrigin: "center center" });
    gsap.set(agentHero, { y: 82, autoAlpha: 0, clipPath: "inset(0% 0% 100% 0%)" });
    gsap.set(agentVisual, { x: 56, scale: 0.96, autoAlpha: 0 });
    gsap.set(agentPortrait, { scale: 1.025, x: 10, transformOrigin: "center center" });
    gsap.set(firstCards.filter(Boolean), { y: 24, autoAlpha: 0 });

    const timeline = gsap.timeline({
      defaults: { ease: "expo.out" },
      onComplete: () => {
        document.body.classList.remove("motion-running");
        document.body.classList.add("motion-complete");
        gsap.set(overlay, { autoAlpha: 0, visibility: "hidden" });
        gsap.set(agentHero, { clearProps: "clipPath" });
        setupScrollAnimations();
        window.ScrollTrigger.refresh();
      },
    });

    timeline
      .fromTo(".opening-kicker", { y: 28, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: 0.5 }, 0.08)
      .fromTo(".opening-title span", { yPercent: 115, scaleX: 0.72, autoAlpha: 0 }, { yPercent: 0, scaleX: 1, autoAlpha: 1, duration: 0.82, stagger: 0.08 }, 0.18)
      .to(".opening-scan", { scaleX: 1, duration: 0.68 }, 0.44)
      .to(openingIllustration, { x: 0, autoAlpha: 1, clipPath: "inset(0% 0% 0% 0%)", duration: 0.88, ease: "power4.out" }, 0.48)
      .to(openingIllustrationImage, { scale: 1, y: 0, duration: 0.96, ease: "power4.out" }, 0.54)
      .fromTo(".opening-meta", { y: 18, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: 0.5 }, 0.74)
      .to({}, { duration: 0.5 }, 1.06)
      .add(() => {
        timeline.pause();
        waitForDataReady().finally(() => timeline.resume());
      }, 1.52)
      .to(commandRail, { y: 0, autoAlpha: 1, duration: 0.72 }, 1.58)
      .to(overlay, { clipPath: "inset(0% 0% 100% 0%)", duration: 0.86, ease: "power4.inOut" }, 1.78)
      .to(heroTitle, { yPercent: 0, scaleX: 1, skewY: 0, duration: 0.98 }, 1.84)
      .to(headerSummary, { y: 0, autoAlpha: 1, duration: 0.64 }, 2.04)
      .to(periodControl, { y: 0, autoAlpha: 1, duration: 0.62 }, 2.14)
      .to(agentHero, { y: 0, autoAlpha: 1, clipPath: "inset(0% 0% 0% 0%)", duration: 1.02, ease: "power4.out" }, 2.22)
      .to(agentVisual, { x: 0, scale: 1, autoAlpha: 1, duration: 0.9, ease: "power4.out" }, 2.38)
      .to(agentPortrait, { scale: 1.005, x: 0, duration: 1.18, ease: "power4.out" }, 2.4)
      .to(firstCards.filter(Boolean), { y: 0, autoAlpha: 1, duration: 0.56, stagger: 0.04 }, 2.62);
  }

  function prepareSectionReveal(section, titleSelector, cardSelector) {
    if (!section || section.dataset.motionPrepared) return;
    const gsap = window.gsap;
    const title = $(titleSelector, section);
    const titleInner = title ? $(".motion-title-mask > span", title) : null;
    const copy = $(".panel-heading p, .ledger-heading p", section);
    const cards = $$(cardSelector, section);

    section.dataset.motionPrepared = "true";
    gsap.set(titleInner || title, {
      yPercent: titleInner ? 115 : 0,
      y: titleInner ? 0 : 54,
      autoAlpha: titleInner ? 1 : 0,
      scaleX: titleInner ? 0.86 : 1,
      transformOrigin: "left center",
    });
    gsap.set(copy, { y: 22, autoAlpha: 0 });
    gsap.set(cards, { y: 34, autoAlpha: 0, scale: 0.985 });
  }

  function sectionReveal(section, titleSelector, cardSelector, options = {}) {
    if (!section) return;
    const gsap = window.gsap;
    const title = $(titleSelector, section);
    const titleInner = title ? $(".motion-title-mask > span", title) : null;
    const copy = $(".panel-heading p, .ledger-heading p", section);
    const cards = $$(cardSelector, section);

    const timeline = gsap.timeline({
      scrollTrigger: {
        trigger: section,
        start: "top 78%",
        once: true,
      },
      defaults: { ease: "power4.out" },
    });

    timeline
      .to(titleInner || title, { yPercent: 0, y: 0, autoAlpha: 1, scaleX: 1, duration: options.titleDuration ?? 1.02 })
      .to(copy, { y: 0, autoAlpha: 1, duration: options.copyDuration ?? 0.72 }, "-=0.66")
      .to(cards, {
        y: 0,
        autoAlpha: 1,
        scale: 1,
        duration: options.cardDuration ?? 0.76,
        stagger: options.cardStagger ?? 0.085,
      }, "-=0.42");
  }

  function setupScrollAnimations() {
    const gsap = window.gsap;
    const intelligencePanel = $(".intelligence-panel");
    const ledgerPanel = $(".ledger-panel");

    const intelligenceTargets = ".core-metric, .node-chip, .metric-matrix > div, .analysis-heading, .decision-item, .category-console .mini-heading, .category-row";

    prepareSectionReveal(intelligencePanel, ".panel-heading h2", intelligenceTargets);
    prepareSectionReveal(ledgerPanel, ".ledger-heading h2", ".filter-bar button, .transaction-item, .ledger-pagination");
    sectionReveal(intelligencePanel, ".panel-heading h2", intelligenceTargets, {
      cardDuration: 0.62,
      cardStagger: 0.045,
    });
    sectionReveal(ledgerPanel, ".ledger-heading h2", ".filter-bar button, .transaction-item, .ledger-pagination", {
      cardDuration: 0.48,
      cardStagger: 0.025,
    });

    const agentVisual = $(".agent-visual");
    if (agentVisual && !agentVisual.dataset.motionParallax) {
      agentVisual.dataset.motionParallax = "true";
      gsap.to(agentVisual, {
        y: -34,
        scale: 1.025,
        ease: "none",
        scrollTrigger: {
          trigger: ".agent-hero",
          start: "top top",
          end: "bottom top",
          scrub: 0.8,
        },
      });
    }

    const agentPortrait = $(".agent-portrait");
    if (agentPortrait && !agentPortrait.dataset.motionParallax) {
      agentPortrait.dataset.motionParallax = "true";
      gsap.to(agentPortrait, {
        y: 22,
        scale: 1.025,
        ease: "none",
        scrollTrigger: {
          trigger: ".agent-hero",
          start: "top top",
          end: "bottom top",
          scrub: 0.9,
        },
      });
    }

    const neuralMap = $(".neural-map");
    if (neuralMap && !neuralMap.dataset.motionParallax) {
      neuralMap.dataset.motionParallax = "true";
      gsap.to(neuralMap, {
        y: -30,
        scale: 1.035,
        ease: "none",
        scrollTrigger: {
          trigger: ".intelligence-panel",
          start: "top top",
          end: "bottom top",
          scrub: 0.8,
        },
      });
    }
  }

  function animateDynamicContent(options = {}) {
    if (!initialized || reduceMotion || !hasGsap()) return;
    window.ScrollTrigger.refresh();
    if (options.quiet) return;

    const gsap = window.gsap;
    dynamicAnimationCount += 1;
    const scope = options.scope || "global";
    const ledgerTargets = [
      ...$$(".filter-bar button"),
      ...$$(".transaction-item"),
      ...$$(".ledger-pagination"),
    ];
    const coreTargets = [
      ...$$(".core-metric"),
      ...$$(".node-chip"),
      ...$$(".metric-matrix > div"),
      ...$$(".analysis-heading"),
      ...$$(".decision-item"),
      ...$$(".category-console .mini-heading"),
      ...$$(".category-row"),
    ];
    const animateTargets = (targets, config = {}) => {
      if (!targets.length) return;
      gsap.fromTo(
        targets,
        { y: config.y ?? 18, autoAlpha: 0 },
        {
          y: 0,
          autoAlpha: 1,
          duration: config.duration ?? 0.58,
          stagger: config.stagger ?? 0.035,
          ease: "power3.out",
          overwrite: true,
        },
      );
    };

    if (scope === "ledger") {
      animateTargets(ledgerTargets, { duration: 0.34, stagger: 0.012, y: 12 });
    } else {
      animateTargets(coreTargets);
      animateTargets(ledgerTargets, { duration: 0.34, stagger: 0.012, y: 12 });
    }

    if (dynamicAnimationCount % 4 === 0) {
      window.ScrollTrigger.refresh();
    }
  }

  window.initCfoMotion = async function initCfoMotion() {
    if (initialized) {
      animateDynamicContent({ quiet: true });
      return;
    }

    await waitForStaticReady();

    if (reduceMotion || !hasGsap()) {
      await waitForDataReady();
      document.documentElement.classList.add("motion-reduced");
      document.body.classList.add("motion-ready", "motion-complete");
      document.body.classList.remove("app-loading", "motion-running");
      const overlay = $(".opening-overlay");
      if (overlay) overlay.style.display = "none";
      initialized = true;
      return;
    }

    window.gsap.registerPlugin(window.ScrollTrigger);
    markMotionTargets();
    initialized = true;
    openingAnimation();
  };

  window.refreshCfoMotion = function refreshCfoMotion(options = {}) {
    requestAnimationFrame(() => {
      markMotionTargets();
      animateDynamicContent(options);
    });
  };
})();
