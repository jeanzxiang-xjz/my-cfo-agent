const currency = new Intl.NumberFormat("zh-CN", {
  style: "currency",
  currency: "CNY",
  maximumFractionDigits: 2,
});

const compactCurrency = new Intl.NumberFormat("zh-CN", {
  style: "currency",
  currency: "CNY",
  maximumFractionDigits: 0,
});

const paymentAppNames = {
  wechat: "微信",
  alipay: "支付宝",
};

const chatAvatarAssets = {
  user: new URL("../assets/avatar-user.png", import.meta.url).href,
  agent: new URL("../assets/avatar-cfo.png", import.meta.url).href,
};

// 类别色板只服务于数据编码（构成条、权重条、流水色点），不参与界面配色。
// 同一个分类在所有视图里必须是同一个颜色，切换周期也不能变色，所以按 key 定色。
const CATEGORY_PALETTE = [
  "var(--cat-1)",
  "var(--cat-2)",
  "var(--cat-3)",
  "var(--cat-4)",
  "var(--cat-5)",
  "var(--cat-6)",
  "var(--cat-7)",
];

// 取色顺序，不是随便排的：构成条只画金额最高的 6 类，所以把「通常占比靠前」的
// 分类排在最前面，它们就必然落在不同色槽上。
//
// 这里原先用 key 的哈希取色，26 个分类砸进 7 个槽，分布还极不均匀——
// 实测账本里 top6 只拿到 3 个颜色（外卖和数字服务同色，演出票务、网购、
// 通信充值三个同色）。哈希的「稳定」只保证同一分类不变色，
// 完全不保证同屏的几个分类不撞色。
const CATEGORY_COLOR_ORDER = [
  "food_delivery",
  "entertainment",
  "ecommerce",
  "digital_services",
  "car_charging",
  "telecom",
  "groceries",
  "books",
  "parking",
  "utilities",
  "lottery",
  "personal_transfer",
  "leisure_travel",
  "coffee_tea",
  "fruit",
  "education",
  "healthcare",
  "general_shopping",
  "transport",
  "bakery",
  "property",
  "stationery",
  "auto",
  "credit_repayment",
  "investment",
];

const CATEGORY_COLOR_INDEX = new Map(CATEGORY_COLOR_ORDER.map((key, index) => [key, index]));

function categoryColor(key) {
  const configured = state.categories.find((item) => item.id === key)?.color_token;
  if (configured) return `var(--${configured})`;
  const value = String(key || "uncategorized");
  // 「未分类」和「其他」共用中性灰：它们是兜底桶，不该抢真实分类的颜色。
  if (value === "uncategorized") return "var(--cat-8)";

  const index = CATEGORY_COLOR_INDEX.get(value);
  if (index !== undefined) return CATEGORY_PALETTE[index % CATEGORY_PALETTE.length];

  // 新分类还没进上面的顺序表时的兜底，保证至少是稳定的。
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 31 + value.charCodeAt(i)) >>> 0;
  }
  return CATEGORY_PALETTE[hash % CATEGORY_PALETTE.length];
}

const ledgerPageSize = 10;
const budgetStorageKey = "ericCfoBudgets";
const defaultBudgets = {
  day: 100,
  week: 700,
  month: 3000,
};

const ICONS = {
  empty: `<svg viewBox="0 0 24 24"><path d="M4 7.5h16v11a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 18.5z"/><path d="M4 7.5 6.4 4h11.2L20 7.5"/><path d="M9.6 11.4h4.8"/></svg>`,
  filter: `<svg viewBox="0 0 24 24"><path d="M4 6h16M7 12h10M10 18h4"/></svg>`,
  spark: `<svg viewBox="0 0 24 24"><path d="M4 16.5 9 11l3.4 3.2L20 6.5"/><path d="M15.4 6.5H20V11"/></svg>`,
  mail: `<svg viewBox="0 0 24 24"><rect x="3.5" y="5.5" width="17" height="13" rx="2"/><path d="m4.5 7.5 7.5 5.5 7.5-5.5"/></svg>`,
  alert: `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.8v4.6M12 15.8v.4"/></svg>`,
};

function loadBudgetConfig() {
  try {
    const saved = JSON.parse(localStorage.getItem(budgetStorageKey) || "{}");
    return {
      day: Number(saved.day) > 0 ? Number(saved.day) : defaultBudgets.day,
      week: Number(saved.week) > 0 ? Number(saved.week) : defaultBudgets.week,
      month: Number(saved.month) > 0 ? Number(saved.month) : defaultBudgets.month,
    };
  } catch {
    return { ...defaultBudgets };
  }
}

let state = {
  transactions: [],
  categories: [],
  categoryVersion: 0,
  categoryPrimaryLimit: 5,
  categoryAllowedIcons: [],
  categoryAllowedColors: [],
  categorySelectedId: null,
  categoryDraftNew: false,
  categorySaving: false,
  categoryStatus: "",
  categoryStatusKind: "",
  categoryConfirm: null,
  generatedAt: null,
  period: "today",
  // 自定义区间 { start, end }，两端都是当天零点，end 为闭区间的最后一天。
  // period === "custom" 时它就是全站唯一的时间尺度。
  customRange: null,
  // 从自定义切回去时落到哪一档。
  lastPresetPeriod: "today",
  // 区间选择面板的草稿态，未点「应用」之前不影响页面。
  rangeDraft: null,
  rangeCursor: null,
  rangeHoverKey: null,
  rangeFocusKey: null,
  filter: "all",
  merchantFocus: "",
  ledgerFilterExpanded: false,
  ledgerPage: 1,
  chatHistory: [],
  chatBusy: false,
  syncBusy: false,
  budgets: loadBudgetConfig(),
  trendMode: "day",
  activeTrendSeries: [],
  trendSelected: null,
  classificationPendingCount: 0,
  activeEvidenceUid: null,
  evidencePayload: null,
  evidenceEditing: false,
  evidenceSaving: false,
  evidenceDeleteConfirm: false,
  evidenceDeleting: false,
  returnFocusElement: null,
  chatExpanded: false,
  chatReturnFocusElement: null,
  chatReturnScrollPosition: null,
  chatTransitionCancel: null,
  profileReport: null,
  profileReportStale: false,
  profileReportBusy: false,
  profileReportIndex: 0,
  profileReportPageCount: 0,
  profileReportStageTimer: null,
  profileReportScrollFrame: null,
  // 「试试问」当前抽中的模板 id。文案不存这里：切时段时要用新作用域现场重算。
  promptPicks: [],
  // 快捷提问的三档：guess=猜你想问 / preset=常用 / mine=我的。
  // promptTab 是用户选的那一档（会记住），promptTabActive 是这次渲染真正显示的那一档
  // ——两者只在「选的那档暂时抽不出东西」时不一致。
  promptTab: loadPromptTab(),
  promptTabActive: loadPromptTab(),
  // 上一次渲染时轨道说的是哪一段。只有它变了才放重调动效——后台补分类的轮询
  // 每隔几秒就重渲染一次，跟着放就成了没来由的闪烁。
  promptRailScope: null,
  // 「换一批」「切档」这类用户主动换内容的一次性标记，用完即清。
  promptRailPulse: false,
  // 排序动效进行中：期间不重画分类列表，否则正在滑动的行会被换成新节点。
  categoryReorderAnimating: false,
  categoryReorderTimer: null,
  customPrompts: [],
  customPromptLimit: 12,
  // 管理弹窗里正在编辑的那条 id；null 表示表单处于「新建」状态。
  promptEditing: null,
  promptConfirm: null,
  // 上一次渲染「我的」用的是哪个时段。切时段那一下要让跟随类胶囊动一次。
  promptStatus: "",
  promptStatusKind: "success",
  hasLoaded: false,
};

function $(id) {
  return document.getElementById(id);
}

const reducedMotionQuery = window.matchMedia?.("(prefers-reduced-motion: reduce)");
const transitionWatchers = new WeakMap();

function prefersReducedMotion() {
  return Boolean(reducedMotionQuery?.matches);
}

/**
 * 以真实的 transitionend 作为状态清理时机；fallback 只防止节点被替换、
 * 浏览器丢失事件等异常路径，不再承担视觉节奏。
 */
function afterTransition(element, callback, options = {}) {
  if (!element) {
    callback();
    return () => {};
  }

  transitionWatchers.get(element)?.();
  let settled = false;
  let fallbackTimer = 0;
  const property = options.property || "transform";
  const finish = () => {
    if (settled) return;
    settled = true;
    window.clearTimeout(fallbackTimer);
    element.removeEventListener("transitionend", handleEnd);
    transitionWatchers.delete(element);
    callback();
  };
  const cancel = () => {
    if (settled) return;
    settled = true;
    window.clearTimeout(fallbackTimer);
    element.removeEventListener("transitionend", handleEnd);
    transitionWatchers.delete(element);
  };
  const handleEnd = (event) => {
    if (event.target === element && (!property || event.propertyName === property)) finish();
  };

  transitionWatchers.set(element, cancel);
  if (prefersReducedMotion()) {
    requestAnimationFrame(finish);
    return cancel;
  }

  element.addEventListener("transitionend", handleEnd);
  fallbackTimer = window.setTimeout(finish, options.fallback ?? 480);
  return cancel;
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

function recoveryMessage(error, action) {
  const message = String(error?.message || "").trim();
  if (error instanceof TypeError || /Failed to fetch|NetworkError|fetch/i.test(message)) {
    return `${action}失败，请确认本地服务仍在运行后重试。`;
  }
  return message || `${action}失败，请稍后重试。`;
}

function renderInlineMarkdown(value) {
  const codeSpans = [];
  let html = escapeHtml(value).replace(/`([^`]+)`/g, (_, code) => {
    const token = `@@CODE_SPAN_${codeSpans.length}@@`;
    codeSpans.push(`<code>${escapeHtml(code)}</code>`);
    return token;
  });

  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_, label, href) => {
    return `<a href="${href}" target="_blank" rel="noreferrer">${label}</a>`;
  });
  html = html.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/__([^_\n]+)__/g, "<strong>$1</strong>");
  html = html.replace(/(^|[^\*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");

  codeSpans.forEach((code, index) => {
    html = html.replace(`@@CODE_SPAN_${index}@@`, code);
  });
  return html;
}

function isMarkdownTableSeparator(line) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

function splitMarkdownTableRow(line) {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function renderMarkdownTable(lines) {
  const headers = splitMarkdownTableRow(lines[0]);
  const rows = lines.slice(2).map(splitMarkdownTableRow);
  return `
    <div class="markdown-table-wrap">
      <table>
        <thead>
          <tr>${headers.map((cell) => `<th>${renderInlineMarkdown(cell)}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${rows.map((row) => `<tr>${row.map((cell) => `<td>${renderInlineMarkdown(cell)}</td>`).join("")}</tr>`).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderMarkdown(text) {
  const lines = String(text || "").replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    const fence = line.match(/^```(\w+)?\s*$/);
    if (fence) {
      const code = [];
      index += 1;
      while (index < lines.length && !/^```\s*$/.test(lines[index])) {
        code.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
      continue;
    }

    if (line.includes("|") && index + 1 < lines.length && isMarkdownTableSeparator(lines[index + 1])) {
      const tableLines = [line, lines[index + 1]];
      index += 2;
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        tableLines.push(lines[index]);
        index += 1;
      }
      blocks.push(renderMarkdownTable(tableLines));
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      const level = Math.min(heading[1].length + 3, 6);
      blocks.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      index += 1;
      continue;
    }

    if (/^\s*>\s?/.test(line)) {
      const quoteLines = [];
      while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
        quoteLines.push(lines[index].replace(/^\s*>\s?/, ""));
        index += 1;
      }
      blocks.push(`<blockquote>${quoteLines.map(renderInlineMarkdown).join("<br>")}</blockquote>`);
      continue;
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*[-*]\s+/, ""));
        index += 1;
      }
      blocks.push(`<ul>${items.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join("")}</ul>`);
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\s*\d+\.\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*\d+\.\s+/, ""));
        index += 1;
      }
      blocks.push(`<ol>${items.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join("")}</ol>`);
      continue;
    }

    const paragraph = [];
    while (
      index < lines.length &&
      lines[index].trim() &&
      !/^```/.test(lines[index]) &&
      !/^(#{1,3})\s+/.test(lines[index]) &&
      !/^\s*>\s?/.test(lines[index]) &&
      !/^\s*[-*]\s+/.test(lines[index]) &&
      !/^\s*\d+\.\s+/.test(lines[index]) &&
      !(lines[index].includes("|") && index + 1 < lines.length && isMarkdownTableSeparator(lines[index + 1]))
    ) {
      paragraph.push(lines[index]);
      index += 1;
    }
    blocks.push(`<p>${paragraph.map(renderInlineMarkdown).join("<br>")}</p>`);
  }

  return blocks.join("");
}

/**
 * 回答完成后只确认一次“结果已到达”，不再拆字等待。
 * Markdown、表格和长段落保持完整排版，避免逐字动画拖慢阅读。
 */
function animateSplitText(node) {
  if (!node || prefersReducedMotion()) return;
  node.classList.remove("answer-result-in");
  requestAnimationFrame(() => {
    node.classList.add("answer-result-in");
    node.addEventListener("animationend", () => node.classList.remove("answer-result-in"), { once: true });
  });
}

function setMessageContent(node, role, text, options = {}) {
  if (role === "agent") {
    node.classList.add("markdown-message");
    node.classList.remove("answer-result-in");
    node.innerHTML = renderMarkdown(text);
    if (options.split) animateSplitText(node);
    return;
  }
  node.classList.remove("answer-result-in");
  node.textContent = text;
  if (options.split) animateSplitText(node);
}

function parseDate(value) {
  return value ? new Date(value) : new Date(NaN);
}

function dateKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function sameDay(a, b) {
  return dateKey(a) === dateKey(b);
}

function inSameMonth(date, anchor) {
  return date.getFullYear() === anchor.getFullYear() && date.getMonth() === anchor.getMonth();
}

function startOfWeek(date) {
  const start = new Date(date);
  const day = start.getDay() || 7;
  start.setHours(0, 0, 0, 0);
  start.setDate(start.getDate() - day + 1);
  return start;
}

function inSameWeek(date, anchor) {
  const start = startOfWeek(anchor);
  const end = new Date(start);
  end.setDate(start.getDate() + 7);
  return date >= start && date < end;
}

function getAnchorDate() {
  // 统计口径以用户当前本地时间为准，不能停在最后一笔交易或快照时间。
  // 这样跨过 00:00 后，今日会自然切换到新的一天。
  return new Date();
}

function startOfDay(date) {
  const start = new Date(date);
  start.setHours(0, 0, 0, 0);
  return start;
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function addMonths(date, months) {
  return new Date(date.getFullYear(), date.getMonth() + months, 1);
}

function normalizeAmount(tx) {
  const amount = Math.abs(Number(tx.amount || 0));
  return tx.direction === "inflow" ? -amount : amount;
}

function positiveSpend(tx) {
  return Math.max(normalizeAmount(tx), 0);
}

const CORRECTION_FIELD_LABELS = {
  amount: "金额",
  paid_at: "交易时间",
  merchant: "商户",
};

function transactionCorrectionFields(tx) {
  if (Array.isArray(tx?.correction_fields)) return tx.correction_fields;
  const missing = [];
  if (!(Number(tx?.amount) > 0)) missing.push("amount");
  if (Number.isNaN(parseDate(tx?.paid_at).getTime())) missing.push("paid_at");
  if (!String(tx?.merchant || "").trim()) missing.push("merchant");
  return missing;
}

function needsCorrection(tx) {
  return tx?.analysis_eligible === false || transactionCorrectionFields(tx).length > 0;
}

function correctionTransactions() {
  return state.transactions
    .filter(needsCorrection)
    .sort((a, b) => {
      const aTime = parseDate(a.captured_at || a.created_at).getTime() || 0;
      const bTime = parseDate(b.captured_at || b.created_at).getTime() || 0;
      return bTime - aTime;
    });
}

function analysisTransactions() {
  return state.transactions.filter((tx) => !needsCorrection(tx));
}

function sum(transactions) {
  return transactions.reduce((total, tx) => total + normalizeAmount(tx), 0);
}

function clamp(value, min, max) {
  const safeMax = Math.max(min, max);
  return Math.min(Math.max(value, min), safeMax);
}

/**
 * 自定义区间的半开边界 [start, end)。state.customRange.end 存的是闭区间末日，
 * 查询时统一 +1 天，和后端 compute_period_date_range 的口径保持一致。
 */
function customBounds(range = state.customRange) {
  if (!range?.start || !range?.end) return null;
  return { start: startOfDay(range.start), end: addDays(startOfDay(range.end), 1) };
}

function scopedTransactions(period = state.period) {
  const anchor = getAnchorDate();
  // 自定义区间是第五种作用域，从这里分流，上面所有渲染函数就不用各自长一个分支。
  if (period === "custom") {
    const bounds = customBounds();
    return bounds ? transactionsBetween(bounds.start, bounds.end) : [];
  }
  return analysisTransactions().filter((tx) => {
    const paidAt = parseDate(tx.paid_at);
    if (Number.isNaN(paidAt.getTime())) return false;
    if (paidAt > anchor) return false;
    if (period === "today") return sameDay(paidAt, anchor);
    if (period === "week") return inSameWeek(paidAt, anchor);
    if (period === "month") return inSameMonth(paidAt, anchor);
    return true;
  });
}

function transactionsBetween(start, end) {
  const anchor = getAnchorDate();
  return analysisTransactions().filter((tx) => {
    const paidAt = parseDate(tx.paid_at);
    return !Number.isNaN(paidAt.getTime()) && paidAt >= start && paidAt < end && paidAt <= anchor;
  });
}

function sumBetween(start, end) {
  return sum(transactionsBetween(start, end));
}

function groupByCategory(transactions) {
  return transactions.reduce((acc, tx) => {
    const key = tx.category || "uncategorized";
    if (!acc[key]) acc[key] = { amount: 0, count: 0 };
    acc[key].amount += positiveSpend(tx);
    acc[key].count += 1;
    return acc;
  }, {});
}

function topCategory(transactions) {
  return Object.entries(groupByCategory(transactions)).sort((a, b) => b[1].amount - a[1].amount)[0] || null;
}

function largest(transactions) {
  return [...transactions].sort((a, b) => positiveSpend(b) - positiveSpend(a))[0] || null;
}

/** 商户名做归并键：商户缺失时退回商品名，都没有就当作无法归并。 */
function merchantKey(tx) {
  return (tx.merchant || tx.product || "").trim();
}

/** 按商户聚合，只保留能归并的交易。 */
function groupByMerchant(transactions) {
  return transactions.reduce((acc, tx) => {
    const key = merchantKey(tx);
    if (!key) return acc;
    if (!acc[key]) acc[key] = { amount: 0, count: 0, latest: null, category: tx.category || "uncategorized" };
    acc[key].amount += positiveSpend(tx);
    acc[key].count += 1;
    const paidAt = parseDate(tx.paid_at);
    if (!Number.isNaN(paidAt.getTime()) && (!acc[key].latest || paidAt > acc[key].latest)) acc[key].latest = paidAt;
    return acc;
  }, {});
}

/** 按自然日聚合支出，用于找出周期内花得最狠的一天。 */
function groupByDay(transactions) {
  return transactions.reduce((acc, tx) => {
    const paidAt = parseDate(tx.paid_at);
    if (Number.isNaN(paidAt.getTime())) return acc;
    const key = dateKey(paidAt);
    if (!acc[key]) acc[key] = { amount: 0, count: 0, date: startOfDay(paidAt) };
    acc[key].amount += positiveSpend(tx);
    acc[key].count += 1;
    return acc;
  }, {});
}

function averageConfidence(transactions) {
  if (!transactions.length) return 0;
  return Math.round((transactions.reduce((total, tx) => total + Number(tx.confidence || 0), 0) / transactions.length) * 100);
}

function formatMoney(value) {
  return currency.format(Number(value || 0));
}

function formatMoneyShort(value) {
  const amount = Number(value || 0);
  if (Math.abs(amount) >= 10000) return `${(amount / 10000).toFixed(1)}万`;
  return compactCurrency.format(amount);
}

function displayDate(value) {
  const d = parseDate(value);
  if (Number.isNaN(d.getTime())) return "--";
  return `${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function displayDateTime(value) {
  const d = parseDate(value);
  if (Number.isNaN(d.getTime())) return "--";
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/**
 * 自定义区间的读法。short 用于顶栏分段和句子里的时间状语（7/28–8/12），
 * 完整式用于面板与提问文案（7月28日–8月12日）。首尾同一天时只说一天。
 */
function customRangeLabel(range = state.customRange, { short = false } = {}) {
  if (!range?.start || !range?.end) return "自定义";
  const format = short ? formatShortDate : shortChineseDate;
  if (sameDay(range.start, range.end)) return format(range.start);
  return `${format(range.start)}–${format(range.end)}`;
}

function periodName(period = state.period) {
  if (period === "today") return "今日净支出";
  if (period === "week") return "本周累计支出";
  if (period === "month") return "本月累计支出";
  if (period === "custom") return `${customRangeLabel(state.customRange, { short: true })} 累计支出`;
  return "全部记录支出";
}

function periodLabel(period = state.period) {
  if (period === "today") return "今日";
  if (period === "week") return "本周";
  if (period === "month") return "本月";
  if (period === "custom") return customRangeLabel(state.customRange, { short: true });
  return "全部";
}

function consumptionAnalysisTitle(period = state.period) {
  if (period === "today") return "今日消费分析";
  if (period === "week") return "本周消费分析";
  if (period === "month") return "本月消费分析";
  if (period === "custom") return `${customRangeLabel(state.customRange, { short: true })} 消费分析`;
  return "整体消费分析";
}

// 快捷提问模板：文字随顶部选中的时段变化，避免提问时间词与所选时段语义不匹配。
const QUICK_PROMPT_TEMPLATES = {
  spend: {
    label: { today: "今日支出", week: "本周支出", month: "本月支出", all: "全部支出" },
    question: {
      today: "我今天花了多少钱？",
      week: "我本周花了多少钱？",
      month: "我本月花了多少钱？",
      all: "我一共花了多少钱？",
    },
  },
  largest: {
    question: {
      today: "今天最大的支出是什么？",
      week: "本周最大的支出是什么？",
      month: "本月最大的支出是什么？",
      all: "目前最大的一笔支出是什么？",
    },
  },
  analysis: {
    question: {
      today: "分析下我今天的消费情况",
      week: "分析下我本周的消费情况",
      month: "分析下我本月的消费情况",
      all: "分析下我目前整体的消费情况",
    },
  },
  takeout: {
    question: {
      today: "我今天外卖点得多吗？",
      week: "我本周外卖点得多吗？",
      month: "我本月外卖点得多吗？",
      all: "我最近外卖点得多吗？",
    },
  },
  budget: {
    question: {
      today: "今日预算使用率是多少？",
      week: "本周预算使用率是多少？",
      month: "本月预算使用率是多少？",
      all: "预算使用率是多少？",
    },
  },
};

// 自定义区间没法预先建表，改成把区间读法插进句子里现拼。
function customQuickPrompts() {
  const label = customRangeLabel(state.customRange);
  return {
    spend: { label: "区间支出", question: `${label} 我花了多少钱？` },
    largest: { question: `${label} 最大的支出是什么？` },
    analysis: { question: `分析下我 ${label} 的消费情况` },
    takeout: { question: `${label} 我外卖点得多吗？` },
    // 这段时间没有对应的预算档，问日均比问使用率诚实。
    budget: { question: `${label} 的日均支出是多少？和我的日预算比怎么样？` },
  };
}

function updateQuickPrompts(period = state.period) {
  if (period === "custom" && state.customRange) {
    const templates = customQuickPrompts();
    document.querySelectorAll(".quick-prompts button").forEach((button) => {
      const template = templates[button.dataset.promptKey];
      if (!template) return;
      button.dataset.question = template.question;
      if (template.label) button.textContent = template.label;
    });
    return;
  }
  const key = ["today", "week", "month"].includes(period) ? period : "all";
  document.querySelectorAll(".quick-prompts button").forEach((button) => {
    const template = QUICK_PROMPT_TEMPLATES[button.dataset.promptKey];
    if (!template) return;
    if (template.question[key]) button.dataset.question = template.question[key];
    if (template.label && template.label[key]) button.textContent = template.label[key];
  });
}


/* ------------------------------ 「试试问」问题库 ------------------------------ */

/*
 * 这些问题以前由模型按账本现生成：每次账本一动（同步一封邮件、后台补一次分类、
 * 改个分类名）指纹就变，就得重算一轮，成本持续而收益有限。现在改成本地模板库：
 * 零 token、零后端，问题用当前作用域的数据填空，说的时间也和顶栏严格一致。
 *
 * 时间对齐不只是措辞问题。get_orientation_context 会把选中时段的权威汇总预注入
 * 对话上下文，系统提示词要求这类问题直接引用、不要调工具；问的时段和顶栏一致，
 * 才吃得到这条捷径，不然 Agent 只能一轮轮查，容易撞上工具轮次上限。
 */

const PROMPT_PICK_COUNT = 3;

// 写法沿用旧提示词里验证过的三条：第一人称（要被直接填进输入框）、
// 问题里不出现金额笔数占比（数字是答案的活，写进问题就没必要点了）、
// 只描述行为不评判人（不写「是不是太多了」）。
const PROMPT_LIBRARY = [
  {
    id: "largest_spend",
    family: "amount",
    label: "最大一笔",
    hook: "最贵的那笔，值得看看买了什么",
    needs: (ctx) => ctx.count >= 1,
    question: (ctx) => `${ctx.when}最大的一笔花在哪、买了什么？`,
  },
  {
    id: "small_leaks",
    family: "amount",
    label: "小钱加起来",
    hook: "不起眼的小额，攒起来常常吓人",
    needs: (ctx) => ctx.count >= 8,
    question: (ctx) => `${ctx.when}那些不起眼的小额支出加起来有多少？`,
  },
  {
    id: "top_category",
    family: "category",
    label: "钱花哪最多",
    hook: "先看钱主要流去了哪一类",
    needs: (ctx) => ctx.categoryCount >= 2,
    question: (ctx) => `${ctx.when}我花得最多的是哪一类？`,
  },
  {
    id: "named_category",
    family: "category",
    // label 就用分类名本身，比「某某类支出」更像一个栏目名
    label: (ctx) => ctx.topCategory,
    hook: "看看这一类占了多大分量",
    needs: (ctx) => Boolean(ctx.topCategory) && ctx.categoryCount >= 2,
    question: (ctx) => `${ctx.when}我在${ctx.topCategory}上花了多少，占比高吗？`,
  },
  {
    id: "long_tail",
    family: "category",
    label: "剩下的钱呢",
    hook: "最大那类之外的钱去哪了",
    needs: (ctx) => ctx.categoryCount >= 3,
    question: (ctx) => `${ctx.when}除了最大的那一类，剩下的钱都去哪了？`,
  },
  {
    id: "top_merchant",
    family: "merchant",
    label: "最常去的店",
    hook: "同一家反复出现，值得算算总账",
    needs: (ctx) => Boolean(ctx.topMerchant),
    question: (ctx) => `${ctx.when}我在${ctx.topMerchant}一共花了多少、去了几次？`,
  },
  {
    id: "merchant_spread",
    family: "merchant",
    label: "常去哪几家",
    hook: "消费是集中在几家，还是很散",
    needs: (ctx) => ctx.merchantCount >= 3,
    question: (ctx) => `${ctx.when}我最常去的是哪几家？`,
  },
  {
    id: "late_night",
    family: "rhythm",
    label: "深夜下单",
    hook: "深夜下的单，和白天不是一回事",
    needs: (ctx) => ctx.lateNightCount >= 1,
    question: (ctx) => `${ctx.when}我有多少笔是深夜下的单？`,
  },
  {
    id: "peak_day",
    family: "rhythm",
    label: "哪天花最多",
    hook: "花得最凶的那天，通常有故事",
    needs: (ctx) => ctx.activeDays >= 3,
    question: (ctx) => `${ctx.when}哪一天花得最多，那天都买了什么？`,
  },
  {
    id: "weekend_effect",
    family: "rhythm",
    label: "周末花更多",
    hook: "周末和工作日的花法常常两样",
    needs: (ctx) => ctx.spanDays >= 7 && ctx.activeDays >= 3,
    question: (ctx) => `${ctx.when}我周末花得比工作日多吗？`,
  },
  {
    id: "recurring",
    family: "frequency",
    label: "订阅扣费",
    hook: "反复出现的支出，可能是订阅",
    needs: (ctx) => ctx.count >= 10,
    question: (ctx) => `${ctx.when}有没有反复出现、可能是订阅的支出？`,
  },
  {
    id: "pace",
    family: "frequency",
    label: "一天几笔",
    hook: "看的是频率，不是单笔金额",
    needs: (ctx) => ctx.activeDays >= 5,
    question: (ctx) => `${ctx.when}我平均一天消费几笔？`,
  },
  {
    id: "discretionary",
    family: "discretionary",
    label: "哪些能省",
    hook: "分清必需和可选，才知道能省哪儿",
    needs: (ctx) => ctx.count >= 5,
    question: (ctx) => `${ctx.when}哪些是可买可不买的，能省下多少？`,
  },
  {
    id: "vs_previous",
    family: "compare",
    label: "比之前多吗",
    hook: "和前面同样长的一段比一比",
    needs: (ctx) => ctx.hasPrevious,
    question: (ctx) => `${ctx.when}和前面同样长的一段时间比，我是花多了还是少了？`,
  },
];

/** 模板里的时间状语。沿用 customQuickPrompts 那套读法，两处文案口径一致。 */
function promptWhen(period = state.period) {
  if (period === "custom" && state.customRange) return `${customRangeLabel(state.customRange)} `;
  if (period === "today") return "我今天";
  if (period === "week") return "我本周";
  if (period === "month") return "我本月";
  return "这份账本里，我";
}

/*
 * 填空数据必须和问题说的时间来自同一个作用域，否则会问出「我本周在楼下面馆
 * 花了多少」——而那家店这周一笔都没有。这正是要消除的那种噪音。
 */
function promptContext(period = state.period) {
  const selected = scopedTransactions(period);
  const categories = Object.entries(groupByCategory(selected)).sort((a, b) => b[1].amount - a[1].amount);

  const merchants = new Map();
  let lateNightCount = 0;
  selected.forEach((tx) => {
    const key = merchantKey(tx);
    if (key) merchants.set(key, (merchants.get(key) || 0) + 1);
    const paidAt = parseDate(tx.paid_at);
    if (Number.isNaN(paidAt.getTime())) return;
    const hour = paidAt.getHours();
    if (hour >= 22 || hour < 5) lateNightCount += 1;
  });
  const [topMerchant] = [...merchants.entries()].sort((a, b) => b[1] - a[1]).find(([, n]) => n >= 2) || [];

  // 「比上一段」得先确认前面那段真有数据可比，否则问出来只能得到一句「没有记录」。
  let hasPrevious = false;
  if (selected.length) {
    const bounds = period === "custom" ? customBounds() : null;
    const start = bounds ? bounds.start : startOfDay(Object.values(groupByDay(selected))
      .map((item) => item.date)
      .sort((a, b) => a - b)[0]);
    const days = Math.max(1, elapsedDaysInPeriod(period));
    hasPrevious = transactionsBetween(addDays(start, -days), start).length > 0;
  }

  return {
    when: promptWhen(period),
    count: selected.length,
    categoryCount: categories.length,
    topCategory: categories.length ? categoryLabel(categories[0][0]) : "",
    merchantCount: merchants.size,
    topMerchant: topMerchant || "",
    lateNightCount,
    activeDays: Object.keys(groupByDay(selected)).length,
    spanDays: periodTotalDays(period),
    hasPrevious,
  };
}

function eligiblePrompts(ctx) {
  return PROMPT_LIBRARY.filter((item) => item.needs(ctx));
}

/** 随机抽一批，同一批里 family 不重复——两枚都在问分类，等于只问了一个问题。 */
function rollPrompts({ exclude = [] } = {}) {
  const ctx = promptContext();
  const pool = eligiblePrompts(ctx);
  // 先排除上一批，池子不够时再把它们放回来，保证「换一批」不会把整组换空。
  const fresh = pool.filter((item) => !exclude.includes(item.id));
  const picks = [];
  const families = new Set();
  [fresh, pool].forEach((source) => {
    shuffled(source).forEach((item) => {
      if (picks.length >= PROMPT_PICK_COUNT) return;
      if (families.has(item.family) || picks.some((p) => p.id === item.id)) return;
      picks.push(item);
      families.add(item.family);
    });
  });
  state.promptPicks = picks.map((item) => item.id);
  return state.promptPicks;
}

function shuffled(list) {
  const items = [...list];
  for (let i = items.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [items[i], items[j]] = [items[j], items[i]];
  }
  return items;
}

/* ---------------------------- 快捷提问：三档轨道 ---------------------------- */

/*
 * 三档的分工：guess=模板库现抽的灵感，preset=写死的常用五问，mine=用户自己写的。
 * 三档共用一条轨道、同时只显示一档——.hero-chat 是定高 grid 且 overflow:hidden，
 * 这排每长一行都直接从消息区扣，所以宁可点一下切换，也不并排铺开。
 */

const PROMPT_TABS = ["guess", "preset", "mine"];
const promptTabStorageKey = "cfoPromptTab";

function loadPromptTab() {
  try {
    const saved = localStorage.getItem(promptTabStorageKey);
    return PROMPT_TABS.includes(saved) ? saved : "guess";
  } catch (error) {
    return "guess";
  }
}

/*
 * 没有骨架屏：模板是本地的，渲染是同步的，没有任何可等的东西。
 * 抽不出胶囊（比如空账本）时返回 0，由 renderPromptRail 把这一档整个收起来。
 */
function renderGuessPrompts() {
  const list = $("aiPromptList");
  if (!list) return 0;

  const ctx = promptContext();
  // 切时段后某条可能失效（比如这周没有商户可填），只补掉失效的那条，
  // 其余保持不动——整组跟着时段乱跳会让人以为点错了。
  const kept = state.promptPicks
    .map((id) => PROMPT_LIBRARY.find((item) => item.id === id))
    .filter((item) => item && item.needs(ctx));
  if (kept.length < PROMPT_PICK_COUNT) {
    const families = new Set(kept.map((item) => item.family));
    shuffled(eligiblePrompts(ctx)).forEach((item) => {
      if (kept.length >= PROMPT_PICK_COUNT) return;
      if (families.has(item.family) || kept.some((p) => p.id === item.id)) return;
      kept.push(item);
      families.add(item.family);
    });
  }
  state.promptPicks = kept.map((item) => item.id);

  list.replaceChildren();
  kept.forEach((item) => {
    const question = item.question(ctx);
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.question = question;
    button.textContent = typeof item.label === "function" ? item.label(ctx) : item.label;
    if (item.hook) button.title = item.hook;
    // 读屏时念完整的问题，而不是胶囊上那 4-6 个字的栏目名。
    button.setAttribute("aria-label", question);
    // setChatBusy 只会禁用调用当时已存在的节点，这里补上重新渲染的情况。
    button.disabled = state.chatBusy;
    list.append(button);
  });
  return kept.length;
}

/*
 * 胶囊上那枚时段前缀。用短词而不是 periodLabel：自定义区间的读法是「5/30–8/10」，
 * 塞进一枚 28px 的胶囊会把整条轨道撑开，完整区间留在 title 和 aria-label 里。
 */
function promptChipScope(period = state.period) {
  if (period === "today") return "今日";
  if (period === "week") return "本周";
  if (period === "month") return "本月";
  if (period === "custom") return "区间";
  return "全部";
}

/** 「我的常问」发出去的整句。跟随时段的那些要带上时间状语，才吃得到服务端预注入的汇总。 */
function composeCustomQuestion(item, period = state.period) {
  return item.follow_period ? `${promptWhen(period)}${item.question}` : item.question;
}

function renderMyPrompts() {
  const track = $("promptTrackMine");
  if (!track) return;
  track.replaceChildren();

  if (!state.customPrompts.length) {
    // 空态不留白：一枚虚线胶囊本身就是入口，省掉一句「还没有内容」的说明文字。
    const ghost = document.createElement("button");
    ghost.type = "button";
    ghost.className = "prompt-ghost";
    ghost.dataset.openModal = "promptModal";
    ghost.textContent = state.demo ? "演示模式不能自定义" : "＋ 添加我的常问";
    ghost.disabled = Boolean(state.demo);
    track.append(ghost);
    return;
  }

  state.customPrompts.forEach((item) => {
    const question = composeCustomQuestion(item);
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.question = question;
    // 跟随时段的挂一枚时段前缀——它会跟着顶栏一起变，这正是这类问题和另一类的
    // 全部区别；不跟随的就是光标签，没有时间，也就没有会变的东西。
    if (item.follow_period) {
      const scope = document.createElement("span");
      scope.className = "chip-scope";
      scope.textContent = promptChipScope();
      button.append(scope);
    } else {
      // 没勾「跟随顶栏时段」的，问的就是问题字面本身：既不打时段标签，
      // 也不把顶栏时段发给服务端，免得注入的是「本周」、答的却是全账本。
      button.dataset.questionScope = "free";
    }
    button.append(document.createTextNode(item.label));
    button.title = question;
    button.setAttribute("aria-label", question);
    button.disabled = state.chatBusy;
    track.append(button);
  });
}

/** 自定义区间要连日期一起算进签名，不然「换了一段区间」看着像没变。 */
function promptScopeSignature() {
  if (state.period === "custom" && state.customRange) {
    return `custom:${dateKey(state.customRange.start)}~${dateKey(state.customRange.end)}`;
  }
  return state.period;
}

/*
 * 传送带上货：重启一次 CSS 动画。类名要先摘掉、强制回流、再挂上，
 * 否则连着两次切换只有第一次动。收尾用定时器而不是 animationend——
 * 后者在第一枚结束时就会触发，会把还在跑的后几枚掐掉。
 */
function playTrackFeed(track) {
  if (!track || prefersReducedMotion()) return;
  track.classList.remove("is-feeding");
  void track.offsetWidth;
  track.classList.add("is-feeding");
  window.clearTimeout(Number(track.dataset.feedTimer));
  track.dataset.feedTimer = window.setTimeout(() => track.classList.remove("is-feeding"), 460);
}

/*
 * 框随货走：从换之前那条轨道的实测宽度，过渡到新内容的实测宽度。
 * 这里必须动真的 width——轨道右边紧跟着「换一批 / 管理」那枚按钮，只有布局真的
 * 变了，它才会跟着一起阔出去或收回来，整条框才是一个整体在呼吸。参与节点就这一个，
 * 子元素不超过六枚，这点布局开销买得起。
 */
function flipTrackWidth(track, fromWidth) {
  if (!track || prefersReducedMotion() || !fromWidth) return;
  const toWidth = track.getBoundingClientRect().width;
  // 宽度没怎么变就不要做假动作：那会变成一次没有信息量的抖动。
  if (Math.abs(toWidth - fromWidth) < 2) return;

  const restore = () => {
    window.clearTimeout(Number(track.dataset.widthTimer));
    track.style.transition = "";
    track.style.width = "";
    // 过渡期间轨道比最终窄，渐隐提示可能算错，落定后再量一次。
    syncTrackOverflow();
  };
  restore();
  track.style.transition = "none";
  track.style.width = `${fromWidth}px`;
  void track.offsetWidth;
  track.style.transition = `width var(--dur-3) var(--ease-out)`;
  track.style.width = `${toWidth}px`;
  // transitionend 可能因为打断而不来，留个兜底把内联样式清干净。
  track.addEventListener("transitionend", restore, { once: true });
  track.dataset.widthTimer = window.setTimeout(restore, 520);
}

/*
 * 分段控件里那一格的出场与退场。「猜你想问」会因为账本里抽不出问题而整档消失，
 * 直接 hidden 是「啪」地闪现：控件宽度一跳，旁边两档也跟着弹。
 * 改成把这一格的宽度和内边距一起从 0 长出来——它自己把邻居推开，退场时反过来被挤没。
 * 进 300ms、出 220ms：退场比入场快，这是一贯的取法。
 */
function squeezeTab(tab, visible, { animate = true } = {}) {
  if (!tab) return;
  const squeezing = tab.dataset.squeeze;
  const shown = !tab.hidden && squeezing !== "out";
  if (shown === visible && !squeezing) return;
  if (!animate || prefersReducedMotion()) {
    delete tab.dataset.squeeze;
    tab.style.cssText = "";
    tab.hidden = !visible;
    return;
  }

  window.clearTimeout(Number(tab.dataset.squeezeTimer));
  const settle = () => {
    window.clearTimeout(Number(tab.dataset.squeezeTimer));
    delete tab.dataset.squeeze;
    tab.style.cssText = "";
    tab.hidden = !visible;
  };

  // 先摘掉 hidden 与上一次的内联样式，才量得到这一格真正的宽度
  tab.hidden = false;
  tab.style.cssText = "";
  const padding = getComputedStyle(tab).paddingLeft;
  const natural = tab.getBoundingClientRect().width;
  if (!natural) return settle();

  tab.dataset.squeeze = visible ? "in" : "out";
  tab.style.overflow = "hidden";
  tab.style.whiteSpace = "nowrap";
  tab.style.transition = "none";
  tab.style.width = visible ? "0px" : `${natural}px`;
  tab.style.paddingLeft = visible ? "0px" : padding;
  tab.style.paddingRight = visible ? "0px" : padding;
  tab.style.opacity = visible ? "0" : "1";
  void tab.offsetWidth;

  const duration = visible ? 300 : 220;
  tab.style.transition = `width ${duration}ms var(--ease-out), padding ${duration}ms var(--ease-out), opacity ${Math.round(duration * 0.7)}ms var(--ease-out)`;
  tab.style.width = visible ? `${natural}px` : "0px";
  tab.style.paddingLeft = visible ? padding : "0px";
  tab.style.paddingRight = visible ? padding : "0px";
  tab.style.opacity = visible ? "1" : "0";
  tab.addEventListener("transitionend", settle, { once: true });
  // transitionend 会因为打断而不来，留个兜底
  tab.dataset.squeezeTimer = window.setTimeout(settle, duration + 120);
}

function renderPromptRail() {
  // 换内容之前先量：这就是框「阔/收」的起点，切档时它是上一档那条轨道。
  const previousTrack = document.querySelector(".prompt-track:not([hidden])");
  const previousWidth = previousTrack ? previousTrack.getBoundingClientRect().width : 0;
  const previousText = previousTrack ? previousTrack.textContent : "";
  const scope = promptScopeSignature();
  // 首次渲染不算「变了」：那是入场，不是改口径。
  const firstRender = state.promptRailScope === null;
  const retune = !firstRender && state.promptRailScope !== scope;
  state.promptRailScope = scope;
  const guessCount = renderGuessPrompts();
  renderMyPrompts();

  // 抽不出灵感问题时（今日还没有消费很常见），这一档整个隐藏而不是留条空轨道。
  const usable = { guess: guessCount > 0, preset: true, mine: true };
  // 回落只改这一次渲染，不改用户选的那一档：不然「今日无消费 → 落到常用」之后，
  // 切到本月明明又有得抽了，也再回不到「猜你想问」。
  const active = usable[state.promptTab] ? state.promptTab : "preset";
  state.promptTabActive = active;

  document.querySelectorAll("[data-prompt-tab]").forEach((tab) => {
    const key = tab.dataset.promptTab;
    const isActive = key === active;
    squeezeTab(tab, usable[key], { animate: !firstRender });
    tab.classList.toggle("is-active", isActive);
    tab.setAttribute("aria-selected", String(isActive));
    // tablist 的规矩：只有选中那一枚进 Tab 序列，组内靠左右方向键走。
    tab.tabIndex = isActive ? 0 : -1;
  });
  document.querySelectorAll(".prompt-track").forEach((track) => {
    track.hidden = track.dataset.track !== active;
  });

  const reroll = $("rerollPrompts");
  if (reroll) reroll.hidden = active !== "guess";
  const manage = $("managePrompts");
  if (manage) manage.hidden = active !== "mine" || Boolean(state.demo);

  syncTrackOverflow();

  /*
   * 动效只服务于真的换了内容的那一档。切时段时：
   * - 「常用」和「我的」都是固定板块——那几枚问题是定死的，跟着时段改的只是说法
   *   （今日支出 → 本月支出、本月｜奶茶账 → 全部｜奶茶账），在眼里仍是同一块，
   *   为一次改口整排抖一下是没有信息量的；
   * - 只有「猜你想问」是现抽的，切时段后抽出来的可能真的换了几枚，那才值得走一趟
   *   传送带；抽中的还是原来那几枚就照样不动。
   * 用户主动换内容（换一批、切档）则一律要动——那是对操作的回应，不是数据的变化。
   */
  const track = document.querySelector(`.prompt-track[data-track="${active}"]`);
  const contentChanged =
    active === "guess" && track && track === previousTrack && previousText !== track.textContent;
  if (state.promptRailPulse || (retune && contentChanged)) {
    state.promptRailPulse = false;
    flipTrackWidth(track, previousWidth);
    playTrackFeed(track);
  }
}

/*
 * 右侧渐隐只在真的溢出时挂上。无条件挂的话，胶囊刚好铺满时最后一枚会被擦掉半边，
 * 看着像渲染错了——而那正是最常见的宽度。
 */
function syncTrackOverflow() {
  const track = document.querySelector(`.prompt-track[data-track="${state.promptTabActive}"]`);
  if (!track) return;
  track.classList.toggle("is-scrollable", track.scrollWidth - track.clientWidth > 4);
}

function selectPromptTab(tab, { focus = false } = {}) {
  if (!PROMPT_TABS.includes(tab) || tab === state.promptTab) return;
  state.promptTab = tab;
  try {
    localStorage.setItem(promptTabStorageKey, tab);
  } catch (error) {
    // 隐私模式下写不进去，记不住也不影响这次使用。
  }
  state.promptRailPulse = true;
  renderPromptRail();
  if (focus) document.querySelector(`[data-prompt-tab="${tab}"]`)?.focus({ preventScroll: true });
}

/* --------------------------- 「我的常问」的增删改 --------------------------- */

async function loadCustomPrompts() {
  try {
    const response = await fetch("./api/custom-prompts", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.answer || "我的常问加载失败。");
    state.customPrompts = payload.prompts || [];
    state.customPromptLimit = payload.limit || 12;
  } catch (error) {
    // 这一档是锦上添花，读不到就当空的——不该把整个对话面板拖住。
    state.customPrompts = [];
  }
}

async function reloadCustomPrompts() {
  await loadCustomPrompts();
  renderPromptRail();
  if (!$("promptModal")?.hidden) renderPromptManager();
}

function setPromptStatus(message = "", kind = "success") {
  state.promptStatus = message;
  state.promptStatusKind = kind;
  const node = $("promptSaveStatus");
  if (node) {
    node.textContent = message;
    node.className = `prompt-save-status is-${kind}`;
    node.hidden = !message;
  }
}

function promptById(id) {
  return state.customPrompts.find((item) => item.id === id) || null;
}

function renderPromptRow(item, index) {
  const confirming = state.promptConfirm === item.id;
  const editing = state.promptEditing === item.id;
  const readonly = state.demo ? " disabled" : "";
  return `
    <div class="prompt-row${editing ? " is-editing" : ""}" data-prompt-row="${escapeHtml(item.id)}">
      <div class="prompt-row-copy">
        <strong>${escapeHtml(item.label)}${item.follow_period ? `<em class="prompt-row-flag">跟随时段</em>` : ""}</strong>
        <span>${escapeHtml(composeCustomQuestion(item))}</span>
      </div>
      ${confirming ? `
        <div class="prompt-row-confirm" role="group" aria-label="确认删除${escapeHtml(item.label)}">
          <span>删掉？</span>
          <button type="button" class="prompt-row-danger" data-prompt-delete="${escapeHtml(item.id)}">删除</button>
          <button type="button" data-prompt-cancel-delete>取消</button>
        </div>
      ` : `
        <div class="prompt-row-actions">
          <button type="button" data-prompt-move="up" data-prompt-id="${escapeHtml(item.id)}" aria-label="上移${escapeHtml(item.label)}"${index === 0 ? " disabled" : readonly}>
            <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M8 12.5v-9M4.5 7 8 3.5 11.5 7" /></svg>
          </button>
          <button type="button" data-prompt-move="down" data-prompt-id="${escapeHtml(item.id)}" aria-label="下移${escapeHtml(item.label)}"${index === state.customPrompts.length - 1 ? " disabled" : readonly}>
            <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M8 3.5v9M4.5 9 8 12.5 11.5 9" /></svg>
          </button>
          <button type="button" data-prompt-edit="${escapeHtml(item.id)}" aria-label="编辑${escapeHtml(item.label)}"${readonly}>
            <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M11.2 2.8 13.2 4.8 5.6 12.4 2.8 13.2 3.6 10.4Z" /></svg>
          </button>
          <button type="button" data-prompt-confirm-delete="${escapeHtml(item.id)}" aria-label="删除${escapeHtml(item.label)}"${readonly}>
            <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M3 4.6h10M6.3 4.6V3h3.4v1.6M4.4 4.6l.6 8.4h6l.6-8.4" /></svg>
          </button>
        </div>
      `}
    </div>
  `;
}

function renderPromptManager() {
  const container = $("promptManager");
  if (!container) return;

  const editing = state.promptEditing ? promptById(state.promptEditing) : null;
  const full = state.customPrompts.length >= state.customPromptLimit && !editing;
  const draft = editing || { label: "", question: "", follow_period: true };

  $("promptModalMeta").textContent = `${state.customPrompts.length}/${state.customPromptLimit} 条 · 点胶囊直接提问`;

  container.innerHTML = `
    ${state.demo ? `<p class="prompt-demo-notice">演示模式可以查看常问，但不能新增、编辑或删除。</p>` : ""}
    <div class="prompt-manager-list">
      ${state.customPrompts.length
        ? state.customPrompts.map((item, index) => renderPromptRow(item, index)).join("")
        : `<p class="prompt-list-empty">还没有常问。写一句你天天想问的话，它就会出现在「我的」那一档里。</p>`}
    </div>
    ${state.demo ? "" : `
      <form class="prompt-form" data-prompt-form novalidate>
        <h3>${editing ? "编辑常问" : "新建常问"}</h3>
        <div class="prompt-form-grid">
          <label>
            <span>标签</span>
            <input name="label" type="text" maxlength="6" value="${escapeHtml(draft.label)}" placeholder="奶茶账" ${full ? "disabled" : ""} />
            <small>最多 6 个字</small>
          </label>
          <label>
            <span>问题</span>
            <input name="question" type="text" maxlength="60" value="${escapeHtml(draft.question)}" placeholder="在奶茶上花了多少？" ${full ? "disabled" : ""} />
            <small>接在时间后面的半句，例如「在奶茶上花了多少？」</small>
          </label>
        </div>
        <div class="prompt-scope">
          <label class="prompt-check">
            <input type="checkbox" name="follow_period" ${draft.follow_period ? "checked" : ""} ${full ? "disabled" : ""} />
            <span>跟随顶栏时段</span>
          </label>
          <p class="prompt-preview">发送时会问：<em data-prompt-preview>${escapeHtml(promptPreviewText(draft))}</em></p>
        </div>
        <div class="prompt-form-actions">
          <span id="promptSaveStatus" class="prompt-save-status is-${state.promptStatusKind}" ${state.promptStatus ? "" : "hidden"}>${escapeHtml(state.promptStatus)}</span>
          ${editing ? `<button type="button" class="btn btn-quiet btn-sm" data-prompt-cancel-edit>取消</button>` : ""}
          <button type="submit" class="btn btn-primary btn-sm" ${full ? "disabled" : ""}>${editing ? "保存修改" : "添加"}</button>
        </div>
        ${full ? `<p class="prompt-form-note">已经存满 ${state.customPromptLimit} 条，先删掉一条再加。</p>` : ""}
      </form>
    `}
  `;
}

/** 预览就是把「跟随时段」这层机制显性化：勾上之后到底会问出什么，一眼看到。 */
function promptPreviewText(draft) {
  const question = String(draft.question || "").trim() || "…";
  return draft.follow_period ? `${promptWhen()}${question}` : question;
}

function syncPromptPreview(form) {
  const node = form.querySelector("[data-prompt-preview]");
  if (!node) return;
  node.textContent = promptPreviewText({
    question: form.elements.question.value,
    follow_period: form.elements.follow_period.checked,
  });
}

async function submitPromptForm(form) {
  const payload = {
    label: form.elements.label.value,
    question: form.elements.question.value,
    follow_period: form.elements.follow_period.checked,
  };
  const editingId = state.promptEditing;
  try {
    setPromptStatus("正在保存…", "pending");
    if (editingId) {
      await categoryRequest(`./api/custom-prompts/${encodeURIComponent(editingId)}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
    } else {
      await categoryRequest("./api/custom-prompts", { method: "POST", body: JSON.stringify(payload) });
    }
    state.promptEditing = null;
    state.promptConfirm = null;
    await reloadCustomPrompts();
    setPromptStatus(editingId ? "已保存" : "已添加", "success");
  } catch (error) {
    setPromptStatus(recoveryMessage(error, "保存常问"), "error");
  }
}

async function deleteCustomPrompt(id) {
  try {
    setPromptStatus("正在删除…", "pending");
    await categoryRequest(`./api/custom-prompts/${encodeURIComponent(id)}`, { method: "DELETE" });
    if (state.promptEditing === id) state.promptEditing = null;
    state.promptConfirm = null;
    await reloadCustomPrompts();
    setPromptStatus("已删除", "success");
  } catch (error) {
    state.promptConfirm = null;
    renderPromptManager();
    setPromptStatus(recoveryMessage(error, "删除常问"), "error");
  }
}

async function moveCustomPrompt(id, direction) {
  const ids = state.customPrompts.map((item) => item.id);
  const index = ids.indexOf(id);
  const target = direction === "up" ? index - 1 : index + 1;
  if (index < 0 || target < 0 || target >= ids.length) return;
  [ids[index], ids[target]] = [ids[target], ids[index]];
  // 先本地换位再落库：↑/↓ 要立刻有反应，失败了下面那次 reload 会把顺序拉回来。
  state.customPrompts = ids.map((value) => promptById(value)).filter(Boolean);
  renderPromptManager();
  renderPromptRail();
  try {
    setPromptStatus("正在保存顺序…", "pending");
    await categoryRequest("./api/custom-prompts/order", {
      method: "PUT",
      body: JSON.stringify({ prompt_ids: ids }),
    });
    setPromptStatus("顺序已保存", "success");
  } catch (error) {
    await reloadCustomPrompts();
    setPromptStatus(recoveryMessage(error, "保存顺序"), "error");
  }
}

function categoryLabel(category) {
  return state.categories.find((item) => item.id === category)?.display_name || category || "未分类";
}

function categoryById(category) {
  return state.categories.find((item) => item.id === category) || null;
}

function filterButton(category, options = {}) {
  const label = category === "all" ? "全部" : categoryLabel(category);
  const classes = ["ledger-filter-chip"];
  if (state.filter === category) classes.push("active");
  if (options.current) classes.push("current-extra");
  return `<button class="${classes.join(" ")}" data-filter="${escapeHtml(category)}" type="button" aria-pressed="${state.filter === category}">${escapeHtml(label)}</button>`;
}

function paymentLabel(app) {
  return paymentAppNames[app] || app || "未知渠道";
}

function evidenceSourceLabel(value) {
  const labels = {
    rule: "规则分类",
    llm: "Agent 分类",
    manual: "手动修正",
    legacy: "历史字段",
    none: "尚未分类",
  };
  return labels[value] || value || "未记录";
}

function evidenceField(label, value, { edited = false } = {}) {
  const mark = edited ? `<em class="evidence-edited" title="这个字段被人工校正过">已校正</em>` : "";
  return `<div class="evidence-field${edited ? " is-edited" : ""}"><span>${escapeHtml(label)}${mark}</span><strong>${escapeHtml(value ?? "未识别")}</strong></div>`;
}

/* --------------------- 解析字段的人工兜底编辑 --------------------- */

/** 与后端 EDITABLE_FIELDS 一一对应；改这里必须同步改 server.py。 */
const EVIDENCE_EDIT_FIELDS = [
  { name: "amount", label: "金额", type: "number", attrs: 'step="0.01" min="0.01" inputmode="decimal" required' },
  // step=1 保留秒：不带秒的话，光打开再保存就会把秒抹成 00，被记成一次「校正」。
  { name: "paid_at", label: "交易时间", type: "datetime-local", attrs: 'step="1" required' },
  { name: "merchant", label: "商户", type: "text", attrs: 'maxlength="60" placeholder="未识别"' },
  { name: "thing", label: "消费内容", type: "text", attrs: 'maxlength="40" placeholder="未识别"' },
  { name: "category", label: "分类", type: "select" },
  { name: "payment_app", label: "支付渠道", type: "select" },
  { name: "payment_method", label: "支付方式", type: "text", attrs: 'maxlength="30" placeholder="未识别"' },
  { name: "card_last4", label: "卡片尾号", type: "text", attrs: 'maxlength="4" inputmode="numeric" placeholder="4 位数字"' },
];

/** datetime-local 只认 `YYYY-MM-DDTHH:mm`，且必须是本地时间，不能直接塞 ISO 串。 */
function toLocalInputValue(value) {
  const date = parseDate(value);
  if (!date || Number.isNaN(date.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function evidenceEditControl(field, tx) {
  const id = `evidenceEdit_${field.name}`;
  if (field.type === "select") {
    const current = tx[field.name] || "";
    const blank = field.name === "payment_app" ? `<option value="">未识别</option>` : "";
    const options = field.name === "category"
      ? state.categories.filter((item) => item.is_enabled || item.id === current).map((item) => [item.id, `${item.display_name}${item.is_enabled ? "" : "（已停用）"}`, !item.is_enabled])
      : Object.entries(paymentAppNames).map(([value, label]) => [value, label, false]);
    const list = options
      .map(([value, label, disabled]) => `<option value="${escapeHtml(value)}"${value === current ? " selected" : ""}${disabled && value !== current ? " disabled" : ""}>${escapeHtml(label)}</option>`)
      .join("");
    const inactiveCurrent = field.name === "category" && !categoryById(current)?.is_enabled ? ` data-inactive-current="${escapeHtml(current)}"` : "";
    return `<select id="${id}" name="${field.name}"${inactiveCurrent}>${blank}${list}</select>`;
  }
  const value = field.name === "paid_at" ? toLocalInputValue(tx.paid_at) : (tx[field.name] ?? "");
  return `<input id="${id}" name="${field.name}" type="${field.type}" value="${escapeHtml(String(value))}" ${field.attrs || ""} />`;
}

function parsedFieldsSection(payload, editing) {
  const tx = payload.transaction || {};
  const edited = new Set(payload.edited_fields || []);
  const canEdit = payload.editable !== false;

  if (!editing) {
    return `
      <div class="evidence-section-head">
        <h3 id="parsedHeading">解析字段</h3>
        ${canEdit ? `<button class="btn btn-quiet btn-sm" type="button" data-evidence-edit>校正</button>` : ""}
      </div>
      <div class="evidence-grid">
        ${evidenceField("金额", Number(tx.amount) > 0 ? formatMoney(tx.amount) : null, { edited: edited.has("amount") })}
        ${evidenceField("交易时间", displayDateTime(tx.paid_at), { edited: edited.has("paid_at") })}
        ${evidenceField("商户", tx.merchant, { edited: edited.has("merchant") })}
        ${evidenceField("消费内容", tx.thing || tx.product, { edited: edited.has("thing") })}
        ${evidenceField("分类", categoryLabel(tx.category), { edited: edited.has("category") })}
        ${evidenceField("支付渠道", paymentLabel(tx.payment_app), { edited: edited.has("payment_app") })}
        ${evidenceField("支付方式", tx.payment_method, { edited: edited.has("payment_method") })}
        ${evidenceField("卡片尾号", tx.card_last4 ? `•••• ${tx.card_last4}` : null, { edited: edited.has("card_last4") })}
      </div>
      ${edited.size ? `<p class="evidence-hint">有 ${edited.size} 个字段被人工校正过，重新解析这张截图时会保留。</p>` : ""}
    `;
  }

  return `
    <div class="evidence-section-head">
      <h3 id="parsedHeading">校正解析字段</h3>
    </div>
    <form class="evidence-edit-form" data-evidence-form novalidate>
      <div class="evidence-grid is-editing">
        ${EVIDENCE_EDIT_FIELDS.map((field) => `
          <label class="evidence-field" for="evidenceEdit_${field.name}">
            <span>${escapeHtml(field.label)}</span>
            ${evidenceEditControl(field, tx)}
          </label>
        `).join("")}
      </div>
      <p class="evidence-edit-error" data-evidence-error hidden></p>
      <div class="evidence-edit-actions">
        <span class="evidence-hint">${payload.image_url ? "对照左上角的原始截图核对。" : "这笔没有截图，改动只作用于这条记录。"}</span>
        <button class="btn btn-quiet btn-sm" type="button" data-evidence-cancel>取消</button>
        <button class="btn btn-primary btn-sm" type="submit">保存</button>
      </div>
    </form>
  `;
}

function categorySummary(transactions) {
  const top = topCategory(transactions);
  if (!top) return "暂无场景";
  return `${categoryLabel(top[0])} ${formatMoney(top[1].amount)}`;
}

function emptyState({ icon = "empty", title, hint = "", action = "" }) {
  return `
    <div class="empty-state">
      <span class="empty-state-icon" aria-hidden="true">${ICONS[icon] || ICONS.empty}</span>
      <strong>${escapeHtml(title)}</strong>
      ${hint ? `<span>${escapeHtml(hint)}</span>` : ""}
      ${action}
    </div>
  `;
}

function budgetLabel(mode = state.trendMode) {
  if (mode === "day") return "日预算";
  if (mode === "week") return "周预算";
  return "月预算";
}

/** 顶部周期 → 预算口径。「全部」没有对应预算。 */
function budgetKeyForPeriod(period = state.period) {
  if (period === "today") return "day";
  if (period === "week") return "week";
  if (period === "month") return "month";
  return null;
}

/** 顶部周期 → 趋势刻度。「全部」是历史累计，月度是最接近的粒度。 */
function trendModeForPeriod(period = state.period) {
  // 自定义区间没有天然刻度，按跨度挑一个不会把柱子压成一片的粒度。
  if (period === "custom") {
    const bounds = customBounds();
    if (!bounds) return "month";
    const days = Math.round((bounds.end - bounds.start) / 86400000);
    return days <= 14 ? "day" : days <= 120 ? "week" : "month";
  }
  return budgetKeyForPeriod(period) || "month";
}

function trendModeTitle(mode = state.trendMode) {
  if (mode === "day") return "近7天每日支出";
  if (mode === "week") return "上月至今周度支出";
  return "本年月度支出";
}

function formatShortDate(date) {
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

function weekEndFor(cursor) {
  const day = cursor.getDay() || 7;
  return addDays(cursor, 7 - day);
}

function trendSeries(mode = state.trendMode) {
  const anchor = startOfDay(getAnchorDate());

  if (mode === "day") {
    return Array.from({ length: 7 }, (_, index) => {
      const start = addDays(anchor, index - 6);
      const end = addDays(start, 1);
      return {
        label: formatShortDate(start),
        title: `${start.getMonth() + 1}月${start.getDate()}日`,
        amount: sumBetween(start, end),
        // 起止随序列一起带出去，明细格的「查看这段交易」要用它筛账本
        start,
        end,
        current: index === 6,
      };
    });
  }

  if (mode === "week") {
    const previousMonthStart = new Date(anchor.getFullYear(), anchor.getMonth() - 1, 1);
    const series = [];
    // 从「上月 1 号所在自然周的周一」一路展示到当前周。
    // 起止都遵循周一至周日的完整自然周口径，避免首周被月界硬切后，
    // 用不足 7 天的数据和完整周预算比较。
    let cursor = startOfWeek(previousMonthStart);

    while (cursor <= anchor) {
      const endDate = weekEndFor(cursor);
      const end = addDays(startOfDay(endDate), 1);
      series.push({
        // 跨了两个月，「第 N 周」是「哪个月的第 N 周」说不清，改用周起始日。
        // 完整区间在下方明细格和 tooltip 里给（title 字段），轴上只要能对上号。
        label: formatShortDate(cursor),
        title: `${formatShortDate(cursor)}-${formatShortDate(endDate)}`,
        amount: sumBetween(cursor, end),
        start: cursor,
        end,
      });
      cursor = end;
    }
    if (series.length) series[series.length - 1].current = true;
    return series;
  }

  const yearStart = new Date(anchor.getFullYear(), 0, 1);
  const series = [];
  for (let cursor = yearStart; cursor <= anchor; cursor = addMonths(cursor, 1)) {
    const end = addMonths(cursor, 1);
    series.push({
      label: `${cursor.getMonth() + 1}月`,
      title: `${cursor.getFullYear()}年${cursor.getMonth() + 1}月`,
      amount: sumBetween(cursor, end),
      start: cursor,
      end,
    });
  }
  if (series.length) series[series.length - 1].current = true;
  return series;
}

function currentBudgetSpend(mode = state.trendMode) {
  const anchor = startOfDay(getAnchorDate());
  if (mode === "day") return sumBetween(anchor, addDays(anchor, 1));
  if (mode === "week") {
    const start = startOfWeek(anchor);
    return sumBetween(start, addDays(start, 7));
  }
  const start = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
  return sumBetween(start, addMonths(start, 1));
}

function remainingBudgetDays(mode = state.trendMode) {
  const anchor = startOfDay(getAnchorDate());
  if (mode === "day") return 1;
  if (mode === "week") {
    const end = addDays(startOfWeek(anchor), 7);
    return Math.max(1, Math.ceil((end - anchor) / 86400000));
  }
  const end = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 1);
  return Math.max(1, Math.ceil((end - anchor) / 86400000));
}

/** 当前周期已过去的天数，用于「日均支出」。 */
function elapsedDaysInPeriod(period = state.period) {
  const anchor = startOfDay(getAnchorDate());
  if (period === "today") return 1;
  if (period === "custom") {
    const bounds = customBounds();
    if (!bounds) return 1;
    // 区间可以选到未来，日均只能除以已经过完的天数。
    const end = Math.min(bounds.end.getTime(), addDays(anchor, 1).getTime());
    return Math.max(1, Math.round((end - bounds.start.getTime()) / 86400000));
  }
  if (period === "week") return Math.max(1, Math.round((anchor - startOfWeek(anchor)) / 86400000) + 1);
  if (period === "month") return Math.max(1, anchor.getDate());
  const dates = analysisTransactions()
    .map((tx) => parseDate(tx.paid_at))
    .filter((date) => !Number.isNaN(date.getTime()));
  if (!dates.length) return 1;
  const earliest = startOfDay(new Date(Math.min(...dates)));
  return Math.max(1, Math.round((anchor - earliest) / 86400000) + 1);
}

/**
 * 环比基准。今日不和「昨天一整天」比（口径不对等），
 * 而是和最近 7 天（不含今天）的日均比；周/月则比较上一周期的同期区间，
 * 避免当前周期尚未结束时拿累计值和完整周期硬比。
 */
function comparisonBaseline(period = state.period) {
  const anchor = startOfDay(getAnchorDate());
  if (period === "custom") {
    // 自定义区间没有「上一个自然周期」，就和紧挨着的等长一段比，口径对等。
    const bounds = customBounds();
    if (!bounds) return null;
    const days = elapsedDaysInPeriod("custom");
    return {
      label: `较前 ${days} 天`,
      value: sumBetween(addDays(bounds.start, -days), bounds.start),
    };
  }
  if (period === "today") {
    const total = sumBetween(addDays(anchor, -7), anchor);
    return { label: "较 7 日均值", value: total / 7 };
  }
  if (period === "week") {
    const start = startOfWeek(anchor);
    const elapsedDays = Math.max(1, Math.round((anchor - start) / 86400000) + 1);
    const previousStart = addDays(start, -7);
    return {
      label: "较上周同期",
      value: sumBetween(previousStart, addDays(previousStart, elapsedDays)),
    };
  }
  if (period === "month") {
    const start = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
    const elapsedDays = Math.max(1, Math.round((anchor - start) / 86400000) + 1);
    const previousStart = addMonths(start, -1);
    const previousMonthDays = new Date(
      previousStart.getFullYear(),
      previousStart.getMonth() + 1,
      0,
    ).getDate();
    const comparableDays = Math.min(elapsedDays, previousMonthDays);
    return {
      label: "较上月同期",
      value: sumBetween(previousStart, addDays(previousStart, comparableDays)),
    };
  }
  return null;
}

function trendSubtitle(mode = state.trendMode) {
  if (mode === "day") return "近 7 天每日支出，虚线是日预算。";
  if (mode === "week") return "上月至今周度支出，虚线是周预算。";
  return "本年第一月到当前月，虚线是月预算。";
}

function annotateTrendSeries(series, mode = state.trendMode) {
  const budget = state.budgets[mode] || 0;
  const label = budgetLabel(mode);
  return series.map((item) => {
    const overBy = budget > 0 ? item.amount - budget : 0;
    return {
      ...item,
      budget,
      budgetLabel: label,
      overBudget: overBy > 0,
      overBy: Math.max(overBy, 0),
    };
  });
}

/** 把坐标轴上界收敛到 1/2/2.5/5 × 10ⁿ，避免出现 437 这种刻度。 */
function niceCeil(value) {
  if (!(value > 0)) return 1;
  const exponent = Math.floor(Math.log10(value));
  const base = 10 ** exponent;
  const normalized = value / base;
  const step = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 2.5 ? 2.5 : normalized <= 5 ? 5 : 10;
  return step * base;
}

function trendChartSvg(series, mode) {
  const width = 760;
  const height = 300;
  const padding = { top: 22, right: 16, bottom: 34, left: 56 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const budget = state.budgets[mode] || 0;
  const rawMax = Math.max(...series.map((item) => item.amount), budget, 1);
  const topValue = niceCeil(rawMax * 1.08);
  const band = chartWidth / Math.max(series.length, 1);
  const colWidth = Math.min(band * 0.5, 30);
  const xFor = (index) => padding.left + band * index + band / 2;
  const yFor = (value) => padding.top + chartHeight - (clamp(value, 0, topValue) / topValue) * chartHeight;
  const baseY = padding.top + chartHeight;

  const grid = Array.from({ length: 5 }, (_, index) => {
    const value = (topValue / 4) * index;
    const y = yFor(value);
    return `
      <line class="${index === 0 ? "trend-baseline" : "trend-grid-line"}" x1="${padding.left}" x2="${width - padding.right}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}"></line>
      <text class="trend-axis-value" x="${padding.left - 10}" y="${(y + 3.5).toFixed(1)}" text-anchor="end">${formatMoneyShort(value)}</text>
    `;
  }).join("");

  const budgetY = yFor(budget);
  const budgetGuide = budget > 0
    ? `
      <line class="trend-budget-line" x1="${padding.left}" x2="${width - padding.right}" y1="${budgetY.toFixed(1)}" y2="${budgetY.toFixed(1)}"></line>
      <text class="trend-budget-text" x="${width - padding.right}" y="${Math.max(budgetY - 6, padding.top + 9).toFixed(1)}" text-anchor="end">${escapeHtml(budgetLabel(mode))} ${escapeHtml(formatMoneyShort(budget))}</text>
    `
    : "";

  const columns = series
    .map((point, index) => {
      const x = xFor(index);
      const y = yFor(point.amount);
      const barHeight = Math.max(baseY - y, point.amount > 0 ? 3 : 1);
      const classes = ["trend-col"];
      if (point.overBudget) classes.push("over-budget");
      if (point.current) classes.push("is-current");
      const description = `${point.title}，${formatMoney(point.amount)}${point.overBudget ? `，超出${point.budgetLabel}${formatMoney(point.overBy)}` : ""}`;
      return `
        <g class="trend-slot" data-trend-index="${index}" tabindex="0" role="button" aria-pressed="false" aria-label="${escapeHtml(description)}">
          <rect class="trend-hit-zone" data-trend-index="${index}" x="${(x - band / 2).toFixed(1)}" y="${padding.top}" width="${band.toFixed(1)}" height="${chartHeight}"></rect>
          <rect class="${classes.join(" ")}" data-trend-index="${index}" x="${(x - colWidth / 2).toFixed(1)}" y="${(baseY - barHeight).toFixed(1)}" width="${colWidth.toFixed(1)}" height="${barHeight.toFixed(1)}" rx="3"></rect>
        </g>
        <text class="trend-axis-label${point.current ? " is-current" : ""}" data-trend-index="${index}" x="${x.toFixed(1)}" y="${height - 12}" text-anchor="middle">${escapeHtml(point.label)}</text>
      `;
    })
    .join("");

  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(trendModeTitle(mode))}">
      ${grid}
      ${budgetGuide}
      ${columns}
    </svg>
  `;
}

/**
 * 图表下方的逐期明细。刻意只给三件事：哪一期、花了多少、有没有超预算。
 * 合计 / 均值 / 峰值这类派生指标不放这儿，属于外围模块的事。
 * 每格是个真按钮：点一下会把上面对应的柱子点亮，所以不能是 <li> 纯文本。
 */
function renderTrendBreakdown(series, mode) {
  const budget = state.budgets[mode] || 0;

  $("trendBreakdown").innerHTML = series
    .map((item, index) => {
      const amount = Math.max(item.amount, 0);
      const isEmpty = amount <= 0;
      const note = budget <= 0 ? "未设预算" : item.overBudget ? `超出 ${formatMoney(item.overBy)}` : "未超预算";
      const classes = ["trend-cell"];
      if (item.overBudget) classes.push("is-over");
      if (item.current) classes.push("is-current");
      if (isEmpty) classes.push("is-empty");

      // 格子本身已经是 button（承载点选高亮），箭头不能嵌在里面，
      // 只能并列成兄弟节点；选中/悬停的底色因此挂到外层 li 上。
      //
      // 零金额那一期跳过去只有一个空账本，所以不给入口——但要留一个同宽的占位，
      // 不然这张卡的正文会撑到最右，和邻卡的宽度对不齐。
      const jump = isEmpty
        ? `<span class="trend-cell-jump is-void" aria-hidden="true"></span>`
        : `
          <button
            class="trend-cell-jump"
            type="button"
            data-trend-jump="${index}"
            title="查看这段时间的交易"
            aria-label="查看 ${escapeHtml(item.title)} 的交易明细"
          >
            <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M6 3.5 10.5 8 6 12.5" /></svg>
          </button>
        `;

      return `
        <li class="${classes.join(" ")}">
          <button
            class="trend-cell-body"
            type="button"
            data-trend-index="${index}"
            aria-pressed="false"
            aria-label="高亮 ${escapeHtml(item.title)} 对应的柱子，${escapeHtml(formatMoney(amount))}，${escapeHtml(note)}"
          >
            <span class="trend-cell-label">
              ${escapeHtml(item.title)}
              ${item.current ? '<em class="trend-cell-flag">当前</em>' : ""}
            </span>
            <strong class="trend-cell-amount">${escapeHtml(formatMoney(amount))}</strong>
            <small class="trend-cell-note">${escapeHtml(note)}</small>
          </button>
          ${jump}
        </li>
      `;
    })
    .join("");
}

/** 当前那一期在序列里的下标（日刻度是最后一根；周/月同理）。 */
function currentTrendIndex() {
  const index = state.activeTrendSeries.findIndex((item) => item.current);
  return index >= 0 ? index : null;
}

/**
 * 点选联动：明细格和柱子是同一期数据的两种画法，选中一格另一边必须跟着亮。
 * 这是点击态，不是悬停态——鼠标扫过时依旧什么都不发生（上次去掉悬停联动的结论）。
 *
 * 总有一根柱子是选中的：取消（再点同一格 / 点空白处 / 传 null）一律落回当前那一期，
 * 而不是回到「什么都没选」——右栏永远在算某一期的数，图上就该有对应的高亮。
 *
 * 压暗其余柱子只在「看的不是当前期」时才开：那时才需要一眼定位点的是哪一根；
 * 默认停在当前期时图表保持全亮，趋势本身才读得出来。这条规则和「回到当前」
 * 按钮的显隐是同一个判据，两者同进同退。
 */
function setTrendSelection(index) {
  const fallback = currentTrendIndex();
  const toggled = index === null || index === state.trendSelected ? null : index;
  const next = toggled === null ? fallback : toggled;
  state.trendSelected = next;

  const atCurrent = next === null || next === fallback;
  const chart = $("trendChart");
  chart.classList.toggle("has-selection", !atCurrent);
  chart.querySelectorAll("[data-trend-index]").forEach((node) => {
    const active = Number(node.dataset.trendIndex) === next;
    node.classList.toggle("is-selected", active);
    if (node.classList.contains("trend-slot")) node.setAttribute("aria-pressed", active ? "true" : "false");
  });

  // 选中态挂在外层 li（整张卡变色），aria-pressed 挂在里面那个真按钮上
  $("trendBreakdown")
    .querySelectorAll(".trend-cell-body")
    .forEach((body) => {
      const active = Number(body.dataset.trendIndex) === next;
      body.closest(".trend-cell")?.classList.toggle("is-selected", active);
      body.setAttribute("aria-pressed", active ? "true" : "false");
    });

  // 右侧预算区是同一份选中态的第三种画法：柱子亮了，数字也要跟着换口径。
  renderTrendBudgetPanel();
  // 只有翻看别的一期才滚动，否则弹窗一打开就会在窄屏上自己动一下。
  if (!atCurrent) revealBudgetPanel();
}

/**
 * 窄屏下预算区被挤到图表下方，点了柱子却什么都看不见。
 * 只在它整块落在视口外时才滚，且用 nearest —— 已经看得见就不要动画面。
 */
function revealBudgetPanel() {
  const panel = $("trendBudgetPanel");
  if (!panel) return;
  const rect = panel.getBoundingClientRect();
  if (rect.top < window.innerHeight - 72 && rect.bottom > 0) return;
  panel.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "nearest" });
}

/** 数值换了才动一下，同一个值反复写不该闪。 */
function swapText(node, text) {
  if (!node) return;
  const next = String(text);
  if (node.textContent === next) return;
  node.textContent = next;
  if (prefersReducedMotion()) return;
  node.animate?.(
    [
      { opacity: 0, transform: "translateY(4px)" },
      { opacity: 1, transform: "none" },
    ],
    { duration: 200, easing: "cubic-bezier(0.16, 1, 0.3, 1)" },
  );
}

function trendSpendLabel(mode = state.trendMode) {
  if (mode === "day") return "当日支出";
  if (mode === "week") return "当周支出";
  return "当月支出";
}

function trendScopeText(mode = state.trendMode) {
  if (mode === "day") return "今日";
  if (mode === "week") return "本周";
  return "本月";
}

/**
 * 预算区跟着选中的柱子走，数字一律取那根柱子的值——右栏和图上被高亮的那一期
 * 必须是同一个数（周刻度跨月时，序列里的当周和 currentBudgetSpend 本来就可能不等，
 * 以图表为准）。停在当前那一期是默认态，翻看别的一期才算「查看中」：
 * 玉色边框、「回到当前」按钮、底部那行换成实际支出，都用这个判据。
 *
 * 结余那一格的标题先判超支：超了一律「超出预算」，不分时态；没超再看时态，
 * 还在进行中的说「还能花」（用户此刻真正要问的是还能花多少），
 * 已经过去的那一期是既成事实，叫「结余」。时态本身由上方口径行的胶囊承担。
 * 底部那行也从「日均可用」换成那一期的实际支出——对已完成的区间来说，
 * 日均可用没有意义。
 */
function renderTrendBudgetPanel() {
  const mode = state.trendMode;
  const budget = state.budgets[mode] || 0;
  const index = state.trendSelected;
  const item = index === null ? null : state.activeTrendSeries[index] || null;
  // 停在当前那一期 = 默认态，它同时也是唯一还在进行中的那一期；
  // 翻看别的一期 = 查看中，那一期已经走完。
  const ongoing = item ? Boolean(item.current) : true;
  const inspecting = Boolean(item) && !ongoing;
  const spend = item ? Math.max(item.amount, 0) : currentBudgetSpend(mode);
  const hasBudget = budget > 0;
  const usage = hasBudget ? Math.round((spend / budget) * 100) : null;
  const remaining = budget - spend;
  const average = remaining / remainingBudgetDays(mode);

  $("trendBudgetPanel").classList.toggle("is-inspecting", inspecting);
  swapText($("trendBudgetScopeText"), inspecting ? item.title : trendScopeText(mode));
  swapText($("trendBudgetScopeState"), ongoing ? "进行中" : "已完成");
  $("trendBudgetReset").hidden = !inspecting;

  swapText($("trendBudgetLabel"), budgetLabel(mode));
  swapText($("trendBudgetValue"), formatMoney(budget));
  swapText($("trendBudgetPercent"), hasBudget ? `${usage}%` : "--");
  // 「结余 -¥265」是句病句：超了就直说超了多少，符号和标签不该互相打架。
  const over = hasBudget && remaining < 0;
  const restLabel = over ? "超出预算" : ongoing ? "还能花" : "结余";
  swapText($("trendBudgetRestLabel"), restLabel);
  swapText($("trendBudgetRemaining"), hasBudget ? formatMoney(Math.abs(remaining)) : "--");

  if (inspecting) {
    swapText($("trendBudgetAverageLabel"), trendSpendLabel(mode));
    swapText($("trendBudgetAverage"), formatMoney(spend));
  } else {
    swapText($("trendBudgetAverageLabel"), mode === "day" ? "计算口径" : "日均可用");
    swapText($("trendBudgetAverage"), mode === "day" ? "按今日消费计算" : formatMoney(average));
  }

  const progress = $("trendBudgetProgress");
  progress.style.setProperty("--meter-ratio", String(clamp(usage || 0, 0, 100) / 100));
  const meter = progress.closest(".meter");
  if (meter) meter.dataset.level = !hasBudget ? "ok" : usage > 100 ? "over" : usage >= 80 ? "warn" : "ok";
  $("trendBudgetRemaining").closest(".budget-rest")?.classList.toggle("is-negative", over);
}

function renderTrendModal() {
  const mode = state.trendMode;
  const series = annotateTrendSeries(trendSeries(mode), mode);
  state.activeTrendSeries = series;

  $("trendSubtitle").textContent = trendSubtitle(mode);
  $("trendChart").innerHTML = trendChartSvg(series, mode);
  renderTrendBreakdown(series, mode);
  // 换口径后同一个序号指的是另一段时间，选中态不能沿用；预算区也随之回到当前周期。
  state.trendSelected = null;
  setTrendSelection(null);

  document.querySelectorAll("[data-trend-mode]").forEach((button) => {
    const active = button.dataset.trendMode === mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-checked", active ? "true" : "false");
    button.tabIndex = active ? 0 : -1;
  });
}

function renderBudgetForm() {
  $("dayBudgetInput").value = state.budgets.day;
  $("weekBudgetInput").value = state.budgets.week;
  $("monthBudgetInput").value = state.budgets.month;
  clearBudgetError();
}

function clearBudgetError() {
  const error = $("budgetError");
  error.hidden = true;
  error.textContent = "";
  document.querySelectorAll("#budgetForm .field-control").forEach((node) => node.classList.remove("has-error"));
}

function saveBudgets(budgets) {
  state.budgets = budgets;
  localStorage.setItem(budgetStorageKey, JSON.stringify(budgets));
  if (!$("trendModal").hidden) renderTrendModal();
  renderHeroBudget();
}

/* ---------------------------- 分类目录维护 ---------------------------- */

const CATEGORY_ICON_PATHS = {
  cup: '<path d="M4 8h12v7a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5Z"/><path d="M16 9h2a3 3 0 0 1 0 6h-2M7 3v2M12 3v2"/>',
  meal: '<path d="M5 3v6a3 3 0 0 0 6 0V3M8 3v18M19 21V3c-3 2-4 5-4 9h4"/>',
  car: '<path d="m3 11 2-6h14l2 6v8H3ZM3 11h18M6 19v2M18 19v2M7 15h1M16 15h1"/>',
  bolt: '<path d="m13 2-9 12h7l-1 8L20 9h-7Z"/>',
  bag: '<path d="M4 8h16l-1 13H5ZM8 8V6a4 4 0 0 1 8 0v2"/>',
  fruit: '<path d="M12 8c-5-3-10 0-8 6 1 4 3 8 8 6 5 2 7-2 8-6 2-6-3-9-8-6ZM12 8V5M12 5c0-3 3-3 5-3 0 3-2 4-5 3Z"/>',
  book: '<path d="M3 4h5a4 4 0 0 1 4 4v13a4 4 0 0 0-4-2H3ZM21 4h-5a4 4 0 0 0-4 4v13a4 4 0 0 1 4-2h5Z"/>',
  cart: '<path d="M2 3h3l3 12h11l3-9H6"/><circle cx="9" cy="20" r="1"/><circle cx="18" cy="20" r="1"/>',
  train: '<rect x="5" y="3" width="14" height="15" rx="3"/><path d="M5 10h14M9 14h.01M15 14h.01M8 18l-2 3M16 18l2 3"/>',
  heart: '<path d="M12 21 4 13C-2 7 6 0 12 7c6-7 14 0 8 6Z"/>',
  home: '<path d="m3 10 9-7 9 7M5 9v12h14V9M9 21v-8h6v8"/>',
  phone: '<rect x="6" y="2" width="12" height="20" rx="2"/><path d="M10 18h4"/>',
  ticket: '<path d="M3 6h18v4a2 2 0 0 0 0 4v4H3v-4a2 2 0 0 0 0-4ZM15 6v3M15 15v3"/>',
  wallet: '<path d="M20 8V5H6a3 3 0 0 0 0 6h15v10H6a3 3 0 0 1-3-3V8"/><path d="M21 14h-5v4h5"/>',
  drop: '<path d="M12 2S5 10 5 15a7 7 0 0 0 14 0c0-5-7-13-7-13Z"/>',
  pencil: '<path d="m4 16-1 5 5-1L21 7l-4-4ZM14 6l4 4"/>',
  screen: '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',
  plane: '<path d="m3 10 18-7-7 18-3-8ZM11 13l5-5"/>',
  gift: '<path d="M4 11v10h16V11M12 7v14"/><path d="M3 7h18v4H3ZM12 7C5 7 5 2 8 2c2 0 4 5 4 5Zm0 0c7 0 7-5 4-5-2 0-4 5-4 5Z"/>',
  transfer: '<path d="M3 7h17l-4-4M20 7l-4 4M21 17H4l4-4M4 17l4 4"/>',
  circle: '<circle cx="12" cy="12" r="9"/><path d="M12 7v6M12 17h.01"/>',
  pet: '<ellipse cx="5" cy="9" rx="2" ry="2.5"/><ellipse cx="9.5" cy="4.5" rx="1.8" ry="2.5"/><ellipse cx="15" cy="4.5" rx="1.8" ry="2.5"/><ellipse cx="19.5" cy="9" rx="2" ry="2.5"/><path d="M8 14c-4 3-3 7 0 7 2 0 2-1 4-1s2 1 4 1c3 0 4-4 0-7-1-1-2-2-4-2s-3 1-4 2Z"/>',
  medicine: '<path d="m4.5 11.5 7-7a5 5 0 0 1 7 7l-7 7a5 5 0 0 1-7-7ZM8 8l7 7"/>',
  parcel: '<path d="m3 7 9-5 9 5v10l-9 5-9-5ZM3 7l9 5 9-5M12 12v10M7.5 4.5l9 5"/>',
  beauty: '<path d="M8 12h8v9H8ZM9 12V6l6-3v9M8 16h8"/>',
  delivery: '<path d="M3 9h18l-3 12H6ZM3 9l3-4h12l3 4M8 5V2M15 5l2-3M9 14h6"/>',
  apparel: '<path d="m8 3-6 5 4 4 2-2v11h8V10l2 2 4-4-6-5a4 4 0 0 1-8 0Z"/>',
};

const CATEGORY_ICON_LABELS = {
  cup: "杯饮", meal: "餐饮", car: "汽车", bolt: "充电", bag: "购物袋",
  fruit: "水果", book: "图书", cart: "购物车", train: "公共交通", heart: "健康",
  home: "住房", phone: "手机", ticket: "票务", wallet: "钱包", drop: "水电燃",
  pencil: "文具", screen: "数字服务", plane: "旅行", gift: "礼物", transfer: "转账",
  circle: "其他", pet: "宠物", medicine: "药品", parcel: "包裹物流", beauty: "美容",
  delivery: "外卖", apparel: "服饰",
};

function categoryIcon(iconKey) {
  return `<svg class="category-symbol" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${CATEGORY_ICON_PATHS[iconKey] || CATEGORY_ICON_PATHS.circle}</svg>`;
}

function setCategoryStatus(message = "", kind = "success") {
  state.categoryStatus = message;
  state.categoryStatusKind = kind;
  const node = $("categorySaveStatus");
  if (node) {
    node.textContent = message;
    node.className = `category-save-status is-${kind}`;
    node.hidden = !message;
  }
}

/*
 * 排序箭头是「动作」，不是「分类」。原来借 categoryIcon("transfer") 那枚双向箭头，
 * 再靠 CSS 旋转 ±90° 凑方向——旋转一个双向符号得到的还是双向符号，两枚长得一模一样，
 * 每次都得先猜哪个是上、哪个是下。这里给它单独的单向箭头，和「我的常问」那组同款，
 * 全站的排序控件说同一种话。
 */
const ORDER_ARROWS = {
  up: '<path d="M8 12.5v-9M4.5 7 8 3.5 11.5 7" />',
  down: '<path d="M8 3.5v9M4.5 9 8 12.5 11.5 9" />',
};

function orderArrow(direction) {
  return `<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">${ORDER_ARROWS[direction]}</svg>`;
}

function renderCategoryRow(item, { primary = false, index = 0, total = 1 } = {}) {
  const selected = state.categorySelectedId === item.id && !state.categoryDraftNew;
  const readonly = state.demo ? " disabled" : "";
  // 头尾的那一端本来就没得可去。先禁用再说，而不是让人点一下才发现没反应；
  // 一亮一灰摆在一起，顺带也把「哪个是上、哪个是下」讲清楚了。
  const noUp = readonly || index === 0 ? " disabled" : "";
  const noDown = readonly || index === total - 1 ? " disabled" : "";
  return `
    <div class="category-list-row${selected ? " is-selected" : ""}${item.is_enabled ? "" : " is-disabled"}" data-category-row="${escapeHtml(item.id)}"${primary && !state.demo ? ' draggable="true"' : ""}>
      <button class="category-row-main" type="button" data-category-select="${escapeHtml(item.id)}" aria-pressed="${selected}">
        <span class="category-glyph" style="--category-color:${categoryColor(item.id)}">${categoryIcon(item.icon_key)}</span>
        <span class="category-row-copy">
          <strong>${escapeHtml(item.display_name)}</strong>
          <small>${item.transaction_count} 笔历史交易 · ${item.is_system ? "系统" : "自定义"}</small>
        </span>
        ${item.is_enabled ? "" : `<em>已停用</em>`}
      </button>
      ${primary ? `
        <div class="category-row-order" aria-label="调整${escapeHtml(item.display_name)}顺序">
          <button type="button" data-category-move="up" data-category-id="${escapeHtml(item.id)}" aria-label="把${escapeHtml(item.display_name)}上移一位"${noUp}>${orderArrow("up")}</button>
          <button type="button" data-category-move="down" data-category-id="${escapeHtml(item.id)}" aria-label="把${escapeHtml(item.display_name)}下移一位"${noDown}>${orderArrow("down")}</button>
        </div>
      ` : ""}
    </div>
  `;
}

const CATEGORY_REORDER_MS = 260;

/*
 * 换位动效用 FLIP：重画之前记下每行的位置，重画之后把它们按位移量先倒推回原处，
 * 再放着过渡到 0——两行于是擦身而过，而不是「啪」地互换。列表是整段重画的，
 * 没有别的办法把新旧节点接上。
 */
function captureCategoryRowTops() {
  const tops = new Map();
  document.querySelectorAll("#categoryList [data-category-row]").forEach((row) => {
    tops.set(row.dataset.categoryRow, row.getBoundingClientRect().top);
  });
  return tops;
}

function playCategoryReorder(previousTops) {
  if (prefersReducedMotion() || !previousTops?.size) return;
  const rows = [...document.querySelectorAll("#categoryList [data-category-row]")];
  const shifted = [];
  rows.forEach((row) => {
    const before = previousTops.get(row.dataset.categoryRow);
    if (before === undefined) return;
    const delta = before - row.getBoundingClientRect().top;
    if (!delta) return;
    row.style.transition = "none";
    row.style.transform = `translateY(${delta}px)`;
    shifted.push(row);
  });
  if (!shifted.length) return;

  state.categoryReorderAnimating = true;
  /*
   * 必须在这里强制一次回流。倒推和归零如果落在同一帧，浏览器只看到「值没变」，
   * 过渡根本不会启动——行直接就位，等于没做动效。用 rAF 也救不了：rAF 回调仍在
   * 同一帧的样式计算之前。
   */
  void document.getElementById("categoryList")?.offsetHeight;
  shifted.forEach((row) => {
    row.style.transition = `transform ${CATEGORY_REORDER_MS}ms var(--ease-out)`;
    row.style.transform = "";
  });
  window.clearTimeout(state.categoryReorderTimer);
  state.categoryReorderTimer = window.setTimeout(() => {
    state.categoryReorderAnimating = false;
    shifted.forEach((row) => {
      row.style.transition = "";
      row.style.transform = "";
    });
    // 动效期间跳过的那次重画在这里补上：保存失败回滚过顺序的话，以这次为准。
    renderCategoryList();
  }, CATEGORY_REORDER_MS + 60);
}

function renderCategoryList() {
  const primary = state.categories.filter((item) => item.is_enabled && item.is_primary).sort((a, b) => a.primary_order - b.primary_order);
  const other = state.categories.filter((item) => item.is_enabled && !item.is_primary);
  const disabled = state.categories.filter((item) => !item.is_enabled);
  const section = (title, items, options = {}) => `
    <section class="category-list-section">
      <div class="category-list-title"><h3>${title}</h3><span>${items.length}</span></div>
      ${items.length
        ? items.map((item, index) => renderCategoryRow(item, { ...options, index, total: items.length })).join("")
        : `<p class="category-list-empty">这里还没有分类</p>`}
    </section>
  `;
  $("categoryList").innerHTML = `
    ${section("常用分类", primary, { primary: true })}
    ${section("其他分类", other)}
    ${section("已停用", disabled)}
  `;
}

function categoryAppearanceFields(item, disabled) {
  return `
    <fieldset class="category-fieldset"${disabled ? " disabled" : ""}>
      <legend>图标</legend>
      <div class="category-icon-options">
        ${state.categoryAllowedIcons.map((icon) => `
          <label title="${escapeHtml(CATEGORY_ICON_LABELS[icon] || icon)}">
            <input type="radio" name="icon_key" value="${escapeHtml(icon)}" aria-label="${escapeHtml(CATEGORY_ICON_LABELS[icon] || icon)}"${item.icon_key === icon ? " checked" : ""} />
            <span>${categoryIcon(icon)}</span>
          </label>
        `).join("")}
      </div>
    </fieldset>
    <fieldset class="category-fieldset"${disabled ? " disabled" : ""}>
      <legend>颜色</legend>
      <div class="category-color-options">
        ${state.categoryAllowedColors.map((color) => `
          <label title="${escapeHtml(color)}">
            <input type="radio" name="color_token" value="${escapeHtml(color)}"${item.color_token === color ? " checked" : ""} />
            <span style="--swatch:var(--${escapeHtml(color)})"></span>
          </label>
        `).join("")}
      </div>
      <p>颜色会同步用于构成图、图例与交易色点。</p>
    </fieldset>
  `;
}

function renderCategoryEditor() {
  const current = state.categoryDraftNew ? null : categoryById(state.categorySelectedId);
  if (!current && !state.categoryDraftNew) {
    $("categoryEditor").innerHTML = `
      <div class="category-editor-empty">
        <span>${categoryIcon("circle")}</span>
        <h3>选择一个分类</h3>
        <p>查看引用情况，或修改名称、图标与颜色。</p>
      </div>
    `;
    return;
  }

  const item = current || {
    id: "",
    display_name: "",
    icon_key: state.categoryAllowedIcons[0] || "circle",
    color_token: state.categoryAllowedColors[0] || "cat-1",
    is_enabled: true,
    is_primary: false,
    is_system: false,
    is_reserved: false,
    transaction_count: 0,
    merchant_memory_count: 0,
    can_delete: true,
  };
  const readonly = Boolean(state.demo || item.is_reserved);
  const actionDisabled = state.demo ? " disabled" : "";
  const deleteReason = item.can_delete
    ? "没有交易或商户记忆引用，可以安全删除。"
    : `仍有 ${item.transaction_count} 笔交易、${item.merchant_memory_count} 条商户记忆引用，只能停用。`;
  const confirm = state.categoryConfirm;
  $("categoryEditor").innerHTML = `
    <form class="category-edit-form" data-category-form data-mode="${state.categoryDraftNew ? "create" : "edit"}" novalidate>
      <div class="category-editor-head">
        <div>
          <span>${state.categoryDraftNew ? "自定义分类" : item.is_system ? "系统分类" : "自定义分类"}</span>
          <h3>${state.categoryDraftNew ? "新建分类" : escapeHtml(item.display_name)}</h3>
        </div>
        <span id="categorySaveStatus" class="category-save-status is-${escapeHtml(state.categoryStatusKind || "success")}"${state.categoryStatus ? "" : " hidden"}>${escapeHtml(state.categoryStatus)}</span>
      </div>
      <label class="category-name-field" for="categoryNameInput">
        <span>显示名称</span>
        <input id="categoryNameInput" name="display_name" value="${escapeHtml(item.display_name)}" maxlength="20" required${readonly ? " disabled" : ""} />
        <small>改名只影响显示，稳定分类 ID 与历史证据不会改变。</small>
      </label>
      ${categoryAppearanceFields(item, readonly || state.demo)}
      ${state.categoryDraftNew ? "" : `
        <div class="category-toggle-row">
          <span><strong>设为常用</strong><small>在账本筛选栏固定展示，最多 ${state.categoryPrimaryLimit} 个。</small></span>
          <label class="category-switch">
            <input type="checkbox" data-category-primary${item.is_primary ? " checked" : ""}${readonly ? " disabled" : ""} />
            <span aria-hidden="true"></span>
          </label>
        </div>
      `}
      <p class="category-form-error" data-category-error role="alert" hidden></p>
      <div class="category-form-actions">
        <button class="btn btn-primary" type="submit"${readonly ? " disabled" : ""}>${state.categoryDraftNew ? "创建分类" : "保存更改"}</button>
      </div>
      ${state.categoryDraftNew ? "" : `
        <div class="category-danger-zone">
          <div>
            <strong>${item.is_enabled ? "停用分类" : "恢复分类"}</strong>
            <p>${item.is_enabled ? "停用后不再用于新交易，历史交易与统计仍会保留。" : "恢复后可重新用于新交易和常用筛选。"}</p>
          </div>
          <button class="btn btn-quiet" type="button" data-category-toggle-enabled${item.is_reserved ? " disabled" : actionDisabled}>${item.is_enabled ? "停用" : "恢复"}</button>
          ${item.is_system ? "" : `
            <div>
              <strong>删除分类</strong>
              <p>${escapeHtml(deleteReason)}</p>
            </div>
            <button class="btn btn-danger" type="button" data-category-delete${item.can_delete ? "" : " disabled"}${actionDisabled}>删除</button>
          `}
        </div>
      `}
      ${confirm ? `
        <div class="category-confirm" role="alertdialog" aria-labelledby="categoryConfirmTitle">
          <h4 id="categoryConfirmTitle">${confirm === "delete" ? "确认删除这个分类？" : item.is_enabled ? "确认停用这个分类？" : "确认恢复这个分类？"}</h4>
          <p>${confirm === "delete" ? "删除后无法恢复。稳定分类 ID 将不再出现在目录中。" : item.is_enabled ? "它会从常用栏与新交易选择器移除；历史交易、统计和证据仍可查看。" : "它会重新出现在新交易分类选择器中。"}</p>
          <div><button class="btn btn-quiet" type="button" data-category-confirm-cancel>取消</button><button class="btn ${confirm === "delete" ? "btn-danger" : "btn-primary"}" type="button" data-category-confirm-action="${confirm}">确认${confirm === "delete" ? "删除" : item.is_enabled ? "停用" : "恢复"}</button></div>
        </div>
      ` : ""}
    </form>
  `;
}

function renderCategoryManager() {
  const primaryCount = state.categories.filter((item) => item.is_primary).length;
  const enabledCount = state.categories.filter((item) => item.is_enabled).length;
  $("categoryModalMeta").textContent = `常用 ${primaryCount}/${state.categoryPrimaryLimit} · 启用 ${enabledCount} 类`;
  $("categoryDemoNotice").hidden = !state.demo;
  $("newCategoryButton").hidden = Boolean(state.demo);
  // 正在滑动时重画会把行换成新节点，动画断在半路，看着还是瞬间跳位。
  if (!state.categoryReorderAnimating) renderCategoryList();
  renderCategoryEditor();
}

async function categoryRequest(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !payload.ok) throw new Error(payload.answer || `请求失败：HTTP ${response.status}`);
  return payload;
}

async function reloadCategories({ preserveSelection = true } = {}) {
  const selected = preserveSelection ? state.categorySelectedId : null;
  const response = await fetch("./api/categories", { cache: "no-store" });
  const payload = await response.json();
  if (!response.ok || !payload.ok) throw new Error(payload.answer || "分类目录加载失败。");
  state.categories = payload.categories || [];
  state.categoryVersion = payload.version || 0;
  state.categoryPrimaryLimit = payload.primary_limit || 5;
  state.categoryAllowedIcons = payload.allowed_icons || [];
  state.categoryAllowedColors = payload.allowed_colors || [];
  state.demo = Boolean(payload.demo || state.demo);
  state.categorySelectedId = selected && categoryById(selected) ? selected : null;
  if (!$("categoryModal")?.hidden) renderCategoryManager();
}

async function savePrimaryOrder(ids, previousIds) {
  try {
    setCategoryStatus("正在保存…", "pending");
    await categoryRequest("./api/categories/primary-order", { method: "PUT", body: JSON.stringify({ category_ids: ids }) });
    await reloadCategories();
    setCategoryStatus("已保存", "success");
    renderFilters();
  } catch (error) {
    state.categories.forEach((item) => { item.primary_order = previousIds.includes(item.id) ? previousIds.indexOf(item.id) : null; item.is_primary = previousIds.includes(item.id); });
    renderCategoryManager();
    setCategoryStatus(recoveryMessage(error, "保存顺序"), "error");
  }
}

async function patchSelectedCategory(fields, action = "保存分类") {
  const id = state.categorySelectedId;
  if (!id || state.categorySaving) return false;
  state.categorySaving = true;
  setCategoryStatus("正在保存…", "pending");
  try {
    await categoryRequest(`./api/categories/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(fields) });
    state.categoryConfirm = null;
    await reloadCategories();
    setCategoryStatus("已保存", "success");
    renderAll();
    if (state.evidencePayload) renderEvidence(state.evidencePayload, { editing: state.evidenceEditing });
    return true;
  } catch (error) {
    setCategoryStatus(recoveryMessage(error, action), "error");
    return false;
  } finally {
    state.categorySaving = false;
  }
}

/* ------------------------------- 弹窗 ------------------------------- */

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])';
const modalReturnFocus = new Map();

function syncModalPageLock() {
  const hasOpenLayer = ["profileReportModal", "categoryModal", "promptModal", "trendModal", "budgetModal", "syncModal", "evidenceDrawer"]
    .map($)
    .some((layer) => layer && !layer.hidden);
  document.body.classList.toggle("modal-open", hasOpenLayer);
}

function focusableIn(modal) {
  return Array.from(modal.querySelectorAll(FOCUSABLE)).filter((node) => node.offsetParent !== null || node === document.activeElement);
}

function openModal(id) {
  const modal = $(id);
  if (!modal || modal.classList.contains("modal-visible")) return;
  const shell = modal.querySelector(".modal-shell");
  transitionWatchers.get(shell)?.();
  modalReturnFocus.set(id, document.activeElement);
  modal.hidden = false;
  syncModalPageLock();
  if (id === "trendModal") renderTrendModal();
  if (id === "budgetModal") renderBudgetForm();
  if (id === "syncModal") resetSyncModal();
  if (id === "profileReportModal") loadProfileReportForModal();
  if (id === "promptModal") {
    state.promptEditing = null;
    state.promptConfirm = null;
    state.promptStatus = "";
    renderPromptManager();
  }
  if (id === "categoryModal") {
    state.categoryDraftNew = false;
    state.categoryConfirm = null;
    state.categoryStatus = "";
    renderCategoryManager();
  }
  requestAnimationFrame(() => {
    modal.classList.add("modal-visible");
    // 常问管理的第一枚可聚焦元素是「下移」，落在那儿既没用又容易误触；
    // 和人格报告一样把焦点交给外壳，Tab 从头走。
    if (id === "profileReportModal" || id === "promptModal") {
      shell?.focus({ preventScroll: true });
    } else {
      const first = focusableIn(modal).find((node) => !node.classList.contains("modal-close")) || modal.querySelector(".modal-close");
      first?.focus({ preventScroll: true });
    }
  });
}

function closeModal(id) {
  if (id === "rangeModal") $("customPeriodBtn")?.setAttribute("aria-expanded", "false");
  const modal = $(id);
  if (!modal || modal.hidden) return;
  const shell = modal.querySelector(".modal-shell");
  afterTransition(shell, () => {
    if (modal.classList.contains("modal-visible")) return;
    modal.hidden = true;
    syncModalPageLock();
  }, { fallback: 300 });
  modal.classList.remove("modal-visible");
  $("trendTooltip").hidden = true;

  const trigger = modalReturnFocus.get(id);
  modalReturnFocus.delete(id);
  if (trigger && document.contains(trigger)) {
    trigger.focus({ preventScroll: true });
  } else if (id === "categoryModal") {
    state.ledgerFilterExpanded = false;
    renderFilters();
    document.querySelector("[data-category-manage]")?.focus({ preventScroll: true });
  }
}

function topmostOpenModal() {
  return ["rangeModal", "profileReportModal", "categoryModal", "promptModal", "budgetModal", "syncModal", "trendModal"].map($).find((modal) => modal && !modal.hidden) || null;
}

function topmostOpenLayer() {
  return [
    $("evidenceDrawer"),
    topmostOpenModal(),
    state.chatExpanded ? $("heroChat") : null,
  ].find((layer) => layer && !layer.hidden) || null;
}

function trapFocus(event) {
  if (event.key !== "Tab") return;
  const modal = topmostOpenLayer();
  if (!modal) return;
  const nodes = focusableIn(modal);
  if (!nodes.length) return;
  const first = nodes[0];
  const last = nodes[nodes.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  } else if (!modal.contains(document.activeElement)) {
    event.preventDefault();
    first.focus();
  }
}

const PARSE_WARNING_LABELS = {
  missing_amount: "截图中没有识别到金额",
  missing_status: "截图中没有识别到支付状态",
  missing_paid_at: "截图中没有识别到交易时间",
  invalid_paid_at: "截图里的交易时间格式无法解析",
  missing_merchant: "截图中没有识别到商户",
  missing_transaction_id: "截图中没有识别到交易单号",
  invalid_transaction_id: "截图里的交易单号格式无法解析",
  invalid_merchant_order_id: "截图里的商户单号格式无法解析",
};

function parseWarningLabel(warning) {
  if (PARSE_WARNING_LABELS[warning]) return PARSE_WARNING_LABELS[warning];
  if (String(warning).startsWith("rejected_generic_merchant_candidate:")) {
    return "识别到的是页面标题，不足以作为商户名称";
  }
  return "截图中还有字段需要人工核对";
}

function evidenceDeleteSection(payload) {
  if (payload.editable === false) return "";
  if (!state.evidenceDeleteConfirm) {
    return `
      <section class="evidence-danger" aria-labelledby="deleteTransactionHeading">
        <div>
          <h3 id="deleteTransactionHeading">删除这笔记录</h3>
          <p>如果这不是账单详情或无法订正，可以从本地账本永久删除。</p>
        </div>
        <button class="btn btn-danger btn-sm" type="button" data-evidence-delete>删除</button>
      </section>
    `;
  }
  return `
    <section class="evidence-delete-confirm" role="alertdialog" aria-labelledby="deleteTransactionConfirmTitle" aria-describedby="deleteTransactionConfirmCopy">
      <div>
        <h3 id="deleteTransactionConfirmTitle">确认永久删除？</h3>
        <p id="deleteTransactionConfirmCopy">交易及其无其他引用的本地截图、OCR 将一并删除，无法恢复。</p>
      </div>
      <p class="evidence-edit-error" data-evidence-delete-error role="alert" hidden></p>
      <div>
        <button class="btn btn-quiet btn-sm" type="button" data-evidence-delete-cancel>取消</button>
        <button class="btn btn-danger btn-sm" type="button" data-evidence-delete-confirm>永久删除</button>
      </div>
    </section>
  `;
}

function renderEvidence(payload, { editing = false } = {}) {
  state.evidencePayload = payload;
  const tx = payload.transaction || {};
  const warnings = Array.isArray(payload.parse_warnings) ? payload.parse_warnings : [];
  const missing = transactionCorrectionFields(tx);
  const status = $("evidenceStatus");
  status.textContent = missing.length ? "待订正" : tx.classification_status === "pending" ? "等待分类" : "证据完整";
  status.classList.toggle("needs-correction", missing.length > 0);
  $("evidenceTitle").textContent = tx.merchant || tx.product || "未知商户";
  $("evidenceSubtitle").textContent = `${tx.paid_at ? displayDate(tx.paid_at) : "交易时间待补"} · ${Number(tx.amount) > 0 ? formatMoney(tx.amount) : "金额待补"}`;
  $("evidenceContent").innerHTML = `
    ${missing.length ? `
      <div class="evidence-correction-note" role="status">
        <strong>这笔记录已保留，暂未计入消费统计</strong>
        <span>请补全${escapeHtml(missing.map((field) => CORRECTION_FIELD_LABELS[field] || field).join("、"))}，或确认它不是账单后删除。</span>
      </div>
    ` : ""}
    <section class="evidence-section" aria-labelledby="captureHeading">
      <h3 id="captureHeading">原始账单</h3>
      <div class="evidence-image-frame">
        ${payload.image_url
          ? `<img src="${escapeHtml(payload.image_url)}" alt="${escapeHtml(tx.merchant || "交易")}的原始账单截图" />`
          : `<div class="evidence-unavailable">这笔记录没有可用截图。交易字段仍可通过 OCR 文本核查。</div>`}
      </div>
    </section>
    <section class="evidence-section" aria-labelledby="parsedHeading" data-parsed-host>
      ${parsedFieldsSection(payload, editing)}
    </section>
    <section class="evidence-section" aria-labelledby="basisHeading">
      <h3 id="basisHeading">识别依据</h3>
      <div class="evidence-grid">
        ${evidenceField("OCR 解析可信度", Number.isFinite(Number(tx.confidence)) ? `${Math.round(Number(tx.confidence) * 100)}%` : null)}
        ${evidenceField("分类来源", evidenceSourceLabel(tx.classification_source))}
        ${evidenceField("分类可信度", Number(tx.classification_confidence) > 0 ? `${Math.round(Number(tx.classification_confidence) * 100)}%` : "未提供")}
        ${evidenceField("交易编号", tx.transaction_uid)}
      </div>
      ${warnings.length ? `<div class="evidence-warning"><strong>解析提醒</strong>${[...new Set(warnings.map(parseWarningLabel))].map((warning) => `<div>${escapeHtml(warning)}</div>`).join("")}</div>` : `<div class="evidence-note">没有发现仍需处理的解析提醒。分类只使用结构化字段，不会把原始 OCR 文本发送给 DeepSeek。</div>`}
    </section>
    <section class="evidence-section" aria-labelledby="ocrHeading">
      <h3 id="ocrHeading">OCR 原文</h3>
      <pre class="ocr-text">${escapeHtml(payload.ocr_text || "没有保存 OCR 文本。")}</pre>
    </section>
    ${evidenceDeleteSection(payload)}
  `;
}

/** 只换「解析字段」这一段，不重绘整个抽屉，避免截图闪一下、滚动位置跳掉。 */
function setEvidenceEditing(editing) {
  const host = $("evidenceContent")?.querySelector("[data-parsed-host]");
  if (!host || !state.evidencePayload) return;
  state.evidenceEditing = editing;
  host.innerHTML = parsedFieldsSection(state.evidencePayload, editing);
  if (editing) host.querySelector("input, select")?.focus({ preventScroll: true });
  else host.querySelector("[data-evidence-edit]")?.focus({ preventScroll: true });
}

async function saveEvidenceEdits(form) {
  if (state.evidenceSaving) return;
  const uid = state.activeEvidenceUid;
  if (!uid) return;

  const data = new FormData(form);
  const fields = {};
  for (const { name } of EVIDENCE_EDIT_FIELDS) fields[name] = String(data.get(name) ?? "").trim();

  const errorNode = form.querySelector("[data-evidence-error]");
  const submit = form.querySelector('button[type="submit"]');
  const fail = (message) => {
    if (!errorNode) return;
    errorNode.textContent = message;
    errorNode.hidden = false;
  };
  if (errorNode) errorNode.hidden = true;

  // 服务端会再校验一遍，这里只是让明显的错误不用等一个来回。
  if (!fields.amount || !(Number(fields.amount) > 0)) return fail("金额要填一个大于 0 的数字。");
  if (!fields.paid_at) return fail("交易时间不能为空。");

  state.evidenceSaving = true;
  if (submit) {
    submit.disabled = true;
    submit.textContent = "保存中…";
  }
  try {
    const response = await fetch("./api/transaction-edit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ uid, fields }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.answer || `保存失败：HTTP ${response.status}`);
    if (state.activeEvidenceUid !== uid) return;

    state.evidenceDeleteConfirm = false;
    renderEvidence(payload);
    state.evidenceEditing = false;

    // 金额和时间会改变每一个派生视图，重新拉一次快照最省心。
    await Promise.all([loadSnapshot(), reloadCategories()]);
    renderAll();
    if (!$("trendModal").hidden) renderTrendModal();
    window.refreshCfoMotion?.();
    const saved = (payload.saved_fields || []).length;
    if (!saved) showToast("没有需要保存的改动");
    else showToast(payload.persisted ? `已校正 ${saved} 个字段，重新解析这张截图时会保留` : `已校正 ${saved} 个字段`);
  } catch (error) {
    fail(recoveryMessage(error, "保存交易改动"));
  } finally {
    state.evidenceSaving = false;
    if (submit && submit.isConnected) {
      submit.disabled = false;
      submit.textContent = "保存";
    }
  }
}

async function deleteActiveTransaction() {
  if (state.evidenceDeleting || !state.activeEvidenceUid) return;
  const uid = state.activeEvidenceUid;
  const errorNode = $("evidenceContent")?.querySelector("[data-evidence-delete-error]");
  const submit = $("evidenceContent")?.querySelector("[data-evidence-delete-confirm]");
  if (errorNode) errorNode.hidden = true;
  state.evidenceDeleting = true;
  if (submit) {
    submit.disabled = true;
    submit.textContent = "删除中…";
  }
  try {
    const response = await fetch("./api/transaction-delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ uid }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.answer || `删除失败：HTTP ${response.status}`);
    closeEvidence();
    await Promise.all([loadSnapshot(), reloadCategories()]);
    renderAll();
    if (!$("trendModal").hidden) renderTrendModal();
    window.refreshCfoMotion?.();
    showToast("交易及本地证据已删除");
  } catch (error) {
    if (errorNode && errorNode.isConnected) {
      errorNode.textContent = recoveryMessage(error, "删除这笔交易");
      errorNode.hidden = false;
    } else {
      showToast(recoveryMessage(error, "删除这笔交易"), "error");
    }
  } finally {
    state.evidenceDeleting = false;
    if (submit && submit.isConnected) {
      submit.disabled = false;
      submit.textContent = "永久删除";
    }
  }
}

async function openEvidence(transactionUid) {
  if (!transactionUid) return;
  state.activeEvidenceUid = transactionUid;
  state.evidencePayload = null;
  state.evidenceEditing = false;
  state.evidenceDeleteConfirm = false;
  state.returnFocusElement = document.activeElement;
  const drawer = $("evidenceDrawer");
  transitionWatchers.get(drawer.querySelector(".evidence-drawer"))?.();
  const localTx = state.transactions.find((tx) => tx.transaction_uid === transactionUid);
  const localNeedsCorrection = Boolean(localTx && needsCorrection(localTx));
  $("evidenceStatus").textContent = localNeedsCorrection ? "待订正" : "交易证据";
  $("evidenceStatus").classList.toggle("needs-correction", localNeedsCorrection);
  $("evidenceTitle").textContent = localTx?.merchant || localTx?.product || "正在载入";
  $("evidenceSubtitle").textContent = localTx
    ? `${localTx.paid_at ? displayDate(localTx.paid_at) : "交易时间待补"} · ${Number(localTx.amount) > 0 ? formatMoney(localTx.amount) : "金额待补"}`
    : "--";
  $("evidenceContent").innerHTML = `<div class="evidence-loading">正在读取本地截图、OCR 与解析记录…</div>`;
  drawer.hidden = false;
  syncModalPageLock();
  requestAnimationFrame(() => {
    drawer.classList.add("drawer-visible");
    drawer.querySelector('[role="dialog"]')?.focus({ preventScroll: true });
  });

  try {
    const response = await fetch(`./api/transaction-evidence?uid=${encodeURIComponent(transactionUid)}`, { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.answer || `读取失败：HTTP ${response.status}`);
    if (state.activeEvidenceUid === transactionUid) renderEvidence(payload);
  } catch (error) {
    if (state.activeEvidenceUid !== transactionUid) return;
    $("evidenceContent").innerHTML = `<div class="evidence-error"><strong>无法读取这笔交易的证据</strong><span>${escapeHtml(recoveryMessage(error, "读取交易证据"))}</span></div>`;
  }
}

function closeEvidence() {
  const drawer = $("evidenceDrawer");
  if (!drawer || drawer.hidden) return;
  const panel = drawer.querySelector(".evidence-drawer");
  state.activeEvidenceUid = null;
  state.evidencePayload = null;
  state.evidenceEditing = false;
  state.evidenceDeleteConfirm = false;
  afterTransition(panel, () => {
    if (drawer.classList.contains("drawer-visible")) return;
    drawer.hidden = true;
    syncModalPageLock();
  }, { fallback: 300 });
  drawer.classList.remove("drawer-visible");
  if (state.returnFocusElement instanceof HTMLElement) {
    state.returnFocusElement.focus({ preventScroll: true });
  }
}

/* ------------------------------- 轻提示 ------------------------------- */

function showToast(message, tone = "info") {
  const region = $("toastRegion");
  if (!region) return;
  const node = document.createElement("div");
  node.className = "toast";
  node.dataset.tone = tone;
  node.textContent = message;
  node.setAttribute("role", "button");
  node.setAttribute("tabindex", "0");
  node.setAttribute("aria-label", `${message}，点击关闭提示`);
  let autoDismissTimer = 0;
  const dismiss = ({ instant = false } = {}) => {
    window.clearTimeout(autoDismissTimer);
    if (instant || prefersReducedMotion()) {
      node.remove();
      return;
    }
    node.classList.add("is-leaving");
    afterTransition(node, () => node.remove(), { property: "opacity", fallback: 220 });
  };
  node.addEventListener("click", () => dismiss({ instant: true }));
  node.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    dismiss({ instant: true });
  });
  region.appendChild(node);
  autoDismissTimer = window.setTimeout(() => dismiss(), 4200);
}

function acknowledgeAgentStatus() {
  const dot = document.querySelector(".pulse-dot");
  if (!dot || prefersReducedMotion()) return;
  dot.classList.remove("is-acknowledging");
  requestAnimationFrame(() => {
    dot.classList.add("is-acknowledging");
    dot.addEventListener("animationend", () => dot.classList.remove("is-acknowledging"), { once: true });
  });
}

/* ------------------------------- 渲染 ------------------------------- */

function renderHeader() {
  const latest = state.transactions[0];

  $("headerSummary").textContent = latest
    ? `账本已同步 · ${state.transactions.length} 笔记录`
    : "账本还没有数据，可以先同步邮箱账单。";

  const eyebrow = document.querySelector(".agent-eyebrow");
  if (state.demo && eyebrow && !eyebrow.querySelector(".demo-badge")) {
    const badge = document.createElement("span");
    badge.className = "demo-badge";
    badge.textContent = "演示数据";
    eyebrow.appendChild(badge);
  }

  const generated = $("footerGenerated");
  if (generated) {
    generated.textContent = state.generatedAt ? `快照时间 ${displayDateTime(state.generatedAt)}` : "快照时间 --";
  }
}

function renderMetrics() {
  const selected = scopedTransactions(state.period);
  const selectedSpend = sum(selected);
  const maxTx = largest(selected);
  const selectedCategories = Object.keys(groupByCategory(selected));

  $("periodLabel").textContent = periodName();
  $("analysisTitle").textContent = consumptionAnalysisTitle();
  $("coreAmount").textContent = formatMoney(selectedSpend);
  $("primaryMeta").textContent = selected.length
    ? `${selected.length} 笔消费 · ${selectedCategories.length} 个场景 · 最高 ${categorySummary(selected)}`
    : "这个周期还没有记录到消费。";

  renderDelta(selectedSpend);

  // #coreNarrative 归 renderDecisionFeed 管：它要念出实际选中的那几条结论。
  // 「今日」时日均就等于头图那个数字，换成笔均，避免同一个值出现两次。
  const perTransaction = state.period === "today";
  $("avgSpendLabel").textContent = perTransaction ? "笔均支出" : "日均支出";
  $("avgDailySpend").textContent = selected.length
    ? formatMoney(perTransaction ? selectedSpend / selected.length : selectedSpend / elapsedDaysInPeriod())
    : "--";
  $("txnCount").textContent = `${selected.length} 笔`;
  $("largestSpend").textContent = maxTx ? formatMoney(maxTx.amount) : "--";
  $("confidenceScore").textContent = selected.length ? `${averageConfidence(selected)}%` : "--";
  $("signalMeta").textContent = `${periodLabel()} · ${selected.length} 笔样本`;

  const stateChip = $("analysisState");
  stateChip.textContent = selected.length ? "Active" : "Learning";
  stateChip.dataset.state = selected.length ? "active" : "idle";
}

function renderDelta(currentSpend) {
  const node = $("coreDelta");
  const baseline = comparisonBaseline();
  if (!baseline || !(baseline.value > 0)) {
    node.textContent = "";
    node.removeAttribute("data-trend");
    node.hidden = true;
    return;
  }
  const ratio = (currentSpend - baseline.value) / baseline.value;
  const percent = Math.round(Math.abs(ratio) * 100);
  const trend = percent < 2 ? "flat" : ratio > 0 ? "up" : "down";
  node.hidden = false;
  node.dataset.trend = trend;
  node.textContent = trend === "flat" ? `${baseline.label}持平` : `${baseline.label} ${ratio > 0 ? "+" : "−"}${percent}%`;
}

function renderHeroBudget() {
  const key = budgetKeyForPeriod();
  const label = $("heroBudgetLabel");
  const value = $("heroBudgetValue");
  const fill = $("heroBudgetFill");
  const meter = $("heroBudgetMeter");
  const foot = $("heroBudgetFoot");

  if (!key) {
    label.textContent = "预算口径";
    value.textContent = "不适用";
    fill.style.setProperty("--meter-ratio", "0");
    meter.setAttribute("aria-valuenow", "0");
    meter.dataset.level = "ok";
    foot.textContent = state.period === "custom"
      ? "自定义区间没有对应的预算周期，切回今日／本周／本月看进度。"
      : "「全部」是历史累计，没有对应的预算周期。";
    return;
  }

  const budget = state.budgets[key] || 0;
  const spend = sum(scopedTransactions(state.period));
  const usage = budget > 0 ? Math.round((spend / budget) * 100) : 0;
  const remaining = budget - spend;

  label.textContent = budgetLabel(key);
  value.textContent = `${formatMoney(spend)} / ${formatMoney(budget)}`;
  fill.style.setProperty("--meter-ratio", String(clamp(usage, 0, 100) / 100));
  meter.setAttribute("aria-valuenow", String(clamp(usage, 0, 100)));
  meter.setAttribute("aria-valuetext", `已用 ${usage}%`);
  meter.dataset.level = usage > 100 ? "over" : usage >= 80 ? "warn" : "ok";

  foot.innerHTML = budget > 0
    ? remaining >= 0
      ? `已用 <b>${usage}%</b>，还剩 <b>${escapeHtml(formatMoney(remaining))}</b>。`
      : `已超 <b>${escapeHtml(formatMoney(Math.abs(remaining)))}</b>，占预算 <b>${usage}%</b>。`
    : "还没设预算，去「预算」里填一个数就能看到进度。";
}

function renderHeroSpark() {
  const isProfile = state.period === "all";
  const trendContent = $("heroTrendContent");
  const profileContent = $("heroProfileContent");
  const button = $("heroSpark");
  trendContent.hidden = isProfile;
  profileContent.hidden = !isProfile;
  button.classList.toggle("is-profile", isProfile);
  // 画像卡比迷你趋势矮一大截，末行得改成弹性高度把剩下的空间吃掉，
  // 否则 space-between 会在预算块和画像卡之间留一片没有边界的空白。
  button.closest(".hero-figure")?.classList.toggle("has-profile", isProfile);

  if (isProfile) {
    const count = scopedTransactions("all").filter((tx) => positiveSpend(tx) > 0).length;
    $("heroProfileMeta").textContent = count
      ? `基于 ${count} 笔消费，生成专属账单画像`
      : "同步消费记录后，就能生成专属画像";
    $("heroProfileActionLabel").textContent = state.profileReport ? "查看画像" : "生成画像";
    button.setAttribute("aria-label", state.profileReport ? "查看账单人格报告" : "生成账单人格报告");
    return;
  }

  // 走势徽标是 App.jsx 里的静态图形，不吃数据，这里只负责说清这个按钮是干什么的。
  button.setAttribute("aria-label", "查看现金流趋势");
}

/* ------------------------------- 账单人格报告 ------------------------------- */

function clearProfileReportStageTimer() {
  if (state.profileReportStageTimer) window.clearInterval(state.profileReportStageTimer);
  state.profileReportStageTimer = null;
}

function setProfileReportBusy(busy) {
  state.profileReportBusy = busy;
  [$("refreshProfileReport"), $("updateProfileReport")].forEach((button) => {
    if (button) button.disabled = busy;
  });
}

function renderProfileReportLoading() {
  clearProfileReportStageTimer();
  $("profileReportNavigation").hidden = true;
  $("profileReportStale").hidden = true;
  $("refreshProfileReport").hidden = true;
  $("profileReportProgress").textContent = "正在生成";
  $("profileReportPages").innerHTML = `
    <section class="profile-report-state profile-report-loading" aria-label="正在生成账单人格报告">
      <span class="profile-loading-orbit" aria-hidden="true"><i></i><i></i><i></i></span>
      <h3>正在读懂你的消费轨迹</h3>
      <p>这次不只算钱，还要找出藏在账单里的生活节奏。</p>
      <ol class="profile-loading-stages">
        <li class="is-active">整理消费足迹</li>
        <li>提炼长期习惯</li>
        <li>命名消费人格</li>
      </ol>
    </section>
  `;
  let stage = 0;
  state.profileReportStageTimer = window.setInterval(() => {
    stage = Math.min(stage + 1, 2);
    document.querySelectorAll(".profile-loading-stages li").forEach((item, index) => {
      item.classList.toggle("is-active", index === stage);
      item.classList.toggle("is-done", index < stage);
    });
    if (stage === 2) clearProfileReportStageTimer();
  }, 1150);
}

function renderProfileReportError(message) {
  clearProfileReportStageTimer();
  $("profileReportNavigation").hidden = true;
  $("profileReportStale").hidden = true;
  $("refreshProfileReport").hidden = true;
  $("profileReportProgress").textContent = "生成未完成";
  $("profileReportPages").innerHTML = `
    <section class="profile-report-state profile-report-error" role="alert">
      <span class="profile-error-mark" aria-hidden="true">
        <svg viewBox="0 0 48 48"><circle cx="24" cy="24" r="18"/><path d="M24 14v12M24 33v.5"/></svg>
      </span>
      <h3>这次画像没有整理好</h3>
      <p>${escapeHtml(message || "生成过程中遇到问题，请稍后再试。")}</p>
      <button class="btn btn-primary" type="button" data-profile-retry>重新生成</button>
    </section>
  `;
}

function profileCoverageLabel(coverage = {}) {
  const formatDateOnly = (value, fallback) => {
    const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})/);
    return match ? `${match[1]}年${Number(match[2])}月${Number(match[3])}日` : fallback;
  };
  const start = formatDateOnly(coverage.start_date, "最早记录");
  const end = formatDateOnly(coverage.end_date, "现在");
  return `${start} — ${end}`;
}

function renderProfileReport(report) {
  if (!report) return;
  clearProfileReportStageTimer();
  state.profileReport = report;
  state.profileReportIndex = 0;
  const coverage = report.coverage || {};
  const traits = Array.isArray(report.persona?.traits) ? report.persona.traits : [];
  const tags = Array.isArray(report.tags) ? report.tags : [];
  const highlights = Array.isArray(report.highlights) ? report.highlights : [];
  const moments = Array.isArray(report.moments) ? report.moments : [];
  const wellbeing = report.wellbeing && typeof report.wellbeing === "object" ? report.wellbeing : null;
  const wellbeingSignals = Array.isArray(wellbeing?.signals) ? wellbeing.signals : [];
  const takeaways = Array.isArray(report.cfo?.takeaways) ? report.cfo.takeaways : [];
  const suggestions = Array.isArray(report.cfo?.suggestions) ? report.cfo.suggestions : [];
  const pages = [
    `
      <section class="profile-report-page profile-report-cover" data-profile-page="0" aria-label="报告封面">
        <div class="profile-cover-image" aria-hidden="true"></div>
        <div class="profile-cover-content">
          <span class="profile-cover-rule" aria-hidden="true"></span>
          <h3>你的消费人格<br>已经被账本写出来了</h3>
          <p>${escapeHtml(profileCoverageLabel(coverage))}</p>
          <div class="profile-cover-stats">
            <span><b>${escapeHtml(String(coverage.transaction_count || 0))}</b> 笔消费</span>
            <span><b>${escapeHtml(formatMoney(coverage.total_outflow_cny || 0))}</b> 累计支出</span>
            <span><b>${escapeHtml(String(coverage.active_days || 0))}</b> 个活跃日</span>
          </div>
        </div>
      </section>
    `,
    `
      <section class="profile-report-page profile-persona-page" data-profile-page="1" aria-label="消费人格">
        <div class="profile-persona-seal" aria-hidden="true"><span></span><i></i></div>
        <div class="profile-persona-copy">
          <p>如果消费习惯是一种生活流派，你属于</p>
          <h3>${escapeHtml(report.persona?.title || "待命名的生活玩家")}</h3>
          <strong>${escapeHtml(report.persona?.subtitle || "")}</strong>
          <p class="profile-persona-intro">${escapeHtml(report.persona?.intro || report.persona?.summary || "")}</p>
          <ul class="profile-persona-points">
            ${traits.map((trait) => `
              <li>
                <span aria-hidden="true">${escapeHtml(trait.emoji)}</span>
                <div><b>${escapeHtml(trait.label)}</b><p>${escapeHtml(trait.text)}</p></div>
                <small>${escapeHtml(trait.evidence)}</small>
              </li>
            `).join("")}
          </ul>
        </div>
      </section>
    `,
    `
      <section class="profile-report-page profile-tags-page" data-profile-page="2" aria-label="人格标签">
        <div class="profile-page-heading">
          <h3>账单给你的生活贴了这些标签</h3>
          <p>不是印象判断，每一条都能在流水里找到来处。</p>
        </div>
        <div class="profile-tag-list">
          ${tags.map((tag, index) => `
            <article class="profile-tag-row">
              <span aria-hidden="true">${escapeHtml(tag.emoji || String(index + 1).padStart(2, "0"))}</span>
              <div><h4>${escapeHtml(tag.label)}</h4><p>${escapeHtml(tag.reason)}</p></div>
              <small>${escapeHtml(tag.evidence)}</small>
            </article>
          `).join("")}
        </div>
      </section>
    `,
    `
      <section class="profile-report-page profile-highlights-page" data-profile-page="3" aria-label="关键数字">
        <div class="profile-page-heading">
          <h3>三个数字，拼出你的消费节奏</h3>
          <p>总额之外，更能说明习惯的往往是频次、偏好与反复出现的选择。</p>
        </div>
        <div class="profile-highlight-list">
          ${highlights.map((item) => `
            <article class="profile-highlight-item">
              <span class="profile-highlight-emoji" aria-hidden="true">${escapeHtml(item.emoji || "")}</span>
              <strong>${escapeHtml(item.value)}</strong>
              <h4>${escapeHtml(item.label)}</h4>
              <p>${escapeHtml(item.context)}</p>
            </article>
          `).join("")}
        </div>
      </section>
    `,
    `
      <section class="profile-report-page profile-moments-page" data-profile-page="4" aria-label="账单名场面">
        <div class="profile-page-heading">
          <h3>账单里的几个名场面</h3>
          <p>某些选择只出现一次，某些习惯却一直在提醒你：这很像你。</p>
        </div>
        <div class="profile-moment-list">
          ${moments.map((moment) => `
            <article class="profile-moment-row">
              <div>
                <h4><span aria-hidden="true">${escapeHtml(moment.emoji || "")}</span>${escapeHtml(moment.title)}</h4>
                <ul>${(moment.lines || (moment.detail ? [moment.detail] : [])).map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul>
              </div>
              <small>${escapeHtml(moment.evidence)}</small>
            </article>
          `).join("")}
        </div>
      </section>
    `,
    wellbeing ? `
      <section class="profile-report-page profile-wellbeing-page" data-profile-page="5" aria-label="生活健康画像">
        <div class="profile-page-heading">
          <h3>消费时间里，藏着怎样的生活节奏</h3>
          <p>把餐饮付款时段和食物类型放在一起看，试着还原你的作息与饮食习惯。</p>
        </div>
        <div class="profile-wellbeing-layout">
          <div class="profile-wellbeing-overview">
            <span class="profile-wellbeing-confidence" data-confidence="${escapeHtml(wellbeing.confidence || "低")}">
              推测可信度 ${escapeHtml(wellbeing.confidence || "低")}
            </span>
            <h4>${escapeHtml(wellbeing.headline || "账单正在积累生活线索")}</h4>
            <p>${escapeHtml(wellbeing.summary || "目前的付款记录还不足以形成稳定判断。")}</p>
            <div class="profile-wellbeing-reminder">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20.2c4.8-2.7 7.4-6.3 7.4-10.2A4.2 4.2 0 0 0 12 7.2 4.2 4.2 0 0 0 4.6 10c0 3.9 2.6 7.5 7.4 10.2Z"/><path d="M12 7.2v8.4M8.8 11.8 12 15l3.2-3.2"/></svg>
              <div><strong>生活提醒</strong><p>${escapeHtml(wellbeing.reminder || "继续记录，等生活节奏更清晰后再判断。")}</p></div>
            </div>
          </div>
          <ol class="profile-wellbeing-signals">
            ${wellbeingSignals.map((signal) => `
              <li>
                <div class="profile-wellbeing-signal-head">
                  <h4>${escapeHtml(signal.label)}</h4>
                  <span>可信度 ${escapeHtml(signal.confidence || "低")}</span>
                </div>
                <p>${escapeHtml(signal.inference)}</p>
                <small>${escapeHtml(signal.evidence)}</small>
              </li>
            `).join("")}
          </ol>
        </div>
        <p class="profile-wellbeing-disclaimer">${escapeHtml(wellbeing.disclaimer || "付款记录只能提供生活线索，不能替代真实饮食和作息记录。")}</p>
      </section>
    ` : "",
    `
      <section class="profile-report-page profile-cfo-page" data-profile-page="6" aria-label="CFO 总结">
        <div class="profile-cfo-mark" aria-hidden="true"><span>CFO</span></div>
        <div class="profile-cfo-copy">
          <h3>最后，让 CFO 说句实在话</h3>
          <p class="profile-cfo-headline">${escapeHtml(report.cfo?.headline || report.cfo?.verdict || "")}</p>
          <div class="profile-cfo-takeaways">
            ${takeaways.map((item) => `
              <article>
                <span aria-hidden="true">${escapeHtml(item.emoji || "")}</span>
                <div><b>${escapeHtml(item.label)}</b><p>${escapeHtml(item.text)}</p></div>
              </article>
            `).join("")}
          </div>
          <div class="profile-cfo-next">
            <strong>接下来，可以这样做</strong>
            <ul>${suggestions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
          </div>
          <button class="profile-cfo-ask" type="button" data-profile-ask>
            让 CFO 继续解读
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h9M8.5 4.5 12 8l-3.5 3.5" /></svg>
          </button>
        </div>
      </section>
    `,
  ].filter(Boolean);

  state.profileReportPageCount = pages.length;
  $("profileReportPages").innerHTML = pages.join("");
  $("profileReportDots").innerHTML = pages.map((_, index) => `
    <button type="button" role="tab" data-profile-index="${index}" aria-label="查看报告第 ${index + 1} 页" aria-selected="${index === 0 ? "true" : "false"}"></button>
  `).join("");
  $("profileReportNavigation").hidden = false;
  $("refreshProfileReport").hidden = false;
  $("profileReportStale").hidden = !state.profileReportStale;
  renderHeroSpark();
  requestAnimationFrame(() => setProfileReportIndex(0, "auto"));
}

function setProfileReportIndex(index, behavior = "smooth") {
  const viewport = $("profileReportViewport");
  const count = state.profileReportPageCount;
  if (!viewport || !count) return;
  const next = clamp(Number(index) || 0, 0, count - 1);
  state.profileReportIndex = next;
  viewport.scrollTo({ left: viewport.clientWidth * next, top: 0, behavior: prefersReducedMotion() ? "auto" : behavior });
  $("profileReportProgress").textContent = `${next + 1} / ${count}`;
  $("profileReportPrev").disabled = next === 0;
  $("profileReportNext").disabled = next === count - 1;
  $("profileReportDots").querySelectorAll("button").forEach((button, buttonIndex) => {
    const active = buttonIndex === next;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  });
}

async function fetchProfileReportMetadata() {
  const response = await fetch("./api/profile-report", { cache: "no-store" });
  const payload = await response.json();
  if (!response.ok || !payload.ok) throw new Error(payload.answer || `画像读取失败：HTTP ${response.status}`);
  state.profileReport = payload.has_report ? payload.report : null;
  state.profileReportStale = Boolean(payload.stale);
  if (state.period === "all") renderHeroSpark();
  return payload;
}

async function generateProfileReport(force = false) {
  if (state.profileReportBusy) return;
  setProfileReportBusy(true);
  renderProfileReportLoading();
  try {
    const response = await fetch("./api/profile-report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.answer || `生成失败：HTTP ${response.status}`);
    state.profileReport = payload.report;
    state.profileReportStale = false;
    renderProfileReport(payload.report);
  } catch (error) {
    if (state.profileReport) {
      renderProfileReport(state.profileReport);
      showToast(`画像更新失败：${error.message}`, "error");
    } else {
      renderProfileReportError(error.message);
    }
  } finally {
    setProfileReportBusy(false);
  }
}

async function loadProfileReportForModal() {
  if (state.profileReportBusy) return;
  if (state.profileReport) renderProfileReport(state.profileReport);
  try {
    const payload = await fetchProfileReportMetadata();
    if (payload.has_report) {
      renderProfileReport(payload.report);
      return;
    }
    await generateProfileReport(false);
  } catch (error) {
    if (!state.profileReport) renderProfileReportError(error.message);
  }
}

function askFromProfileReport() {
  if (!state.profileReport || state.chatBusy) {
    if (state.chatBusy) showToast("上一个问题还在回答，等它结束再继续。", "info");
    return;
  }
  const report = state.profileReport;
  const labels = (report.tags || []).map((tag) => tag.label).join("、");
  const wellbeing = report.wellbeing?.headline ? `生活健康画像提示“${report.wellbeing.headline}”。` : "";
  const question = `请继续解读我的账单人格报告：消费人格是“${report.persona?.title || ""}”，标签包括${labels}。${wellbeing}结合全部账本，告诉我最值得肯定、最值得调整的消费习惯，并简短补充一条生活健康提醒。`;
  closeModal("profileReportModal");
  window.setTimeout(() => {
    openChatExpanded();
    submitQuestion(question);
  }, prefersReducedMotion() ? 20 : 280);
}

function renderComposition() {
  const selected = scopedTransactions(state.period);
  const grouped = groupByCategory(selected);
  const entries = Object.entries(grouped).sort((a, b) => b[1].amount - a[1].amount);
  const total = entries.reduce((acc, [, value]) => acc + value.amount, 0);

  $("categoryCount").textContent = entries.length ? `${entries.length} 类 · 按金额` : "--";

  if (!entries.length || total <= 0) {
    $("coreNodes").classList.remove("has-data");
    $("coreNodes").innerHTML = emptyState({
      icon: "spark",
      title: "还没有可拆解的消费",
      hint: "同步账单或换一个周期，场景权重会自动出现。",
    });
    return;
  }
  $("coreNodes").classList.add("has-data");

  const top = entries.slice(0, 6);
  const restAmount = entries.slice(6).reduce((acc, [, value]) => acc + value.amount, 0);
  const segments = top.map(([key, value]) => ({
    key,
    label: categoryLabel(key),
    amount: value.amount,
    color: categoryColor(key),
  }));
  if (restAmount > 0) segments.push({ key: "__rest", label: "其他", amount: restAmount, color: "var(--cat-8)" });

  $("coreNodes").innerHTML = `
    <div class="composition-bar" role="img" aria-label="${escapeHtml(segments.map((seg) => `${seg.label} ${Math.round((seg.amount / total) * 100)}%`).join("，"))}">
      ${segments
        .map(
          (seg) =>
            `<span class="composition-seg" style="--segment-weight:${seg.amount.toFixed(2)};--seg-color:${seg.color}"></span>`,
        )
        .join("")}
    </div>
    <ul class="composition-legend">
      ${segments
        .map(
          (seg) => `
            <li>
              <span class="legend-dot" style="--seg-color:${seg.color}" aria-hidden="true"></span>
              ${escapeHtml(seg.label)}
              <b>${Math.round((seg.amount / total) * 100)}%</b>
            </li>
          `,
        )
        .join("")}
    </ul>
  `;
}

/** 周期的完整天数，用于把「已花的钱」按节奏推到周期末。 */
function periodTotalDays(period = state.period) {
  const anchor = startOfDay(getAnchorDate());
  if (period === "custom") {
    const bounds = customBounds();
    return bounds ? Math.max(1, Math.round((bounds.end - bounds.start) / 86400000)) : 1;
  }
  if (period === "week") return 7;
  if (period === "month") return new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0).getDate();
  return elapsedDaysInPeriod(period);
}

function shortChineseDate(date) {
  return `${date.getMonth() + 1}月${date.getDate()}日`;
}

/**
 * 「全部」这个周期词直接塞进句子里不通顺（"全部出现了 12 次"、"占了全部的 24%"），
 * 所以按用途分两套说法：when 用于时间状语，scope 用于「占某某支出」。
 */
function periodPhrase(kind, period = state.period) {
  if (period === "custom") {
    const label = customRangeLabel(state.customRange, { short: true });
    return kind === "scope" ? `${label} 支出` : label;
  }
  const isAll = !["today", "week", "month"].includes(period);
  if (kind === "scope") return isAll ? "全部支出" : `${periodLabel(period)}支出`;
  return isAll ? "累计" : periodLabel(period);
}

/**
 * 分析卡片的候选池。一条结论要进池子，必须同时满足：
 *   1. 说的是别处没说过的事——首屏已经给了总额、环比、预算进度和最大单笔金额，
 *      这里再复述一遍就是浪费一整块面积；
 *   2. 带一个能被核对的数字；
 *   3. 至少有一条去处：能筛出对应明细、能打开原始证据，或者能直接把问题甩给 Agent。
 * 最后按 weight 取前三条。之前是固定三格，样本不够时只能填「继续观察即可」这种
 * 没有信息量的占位话；现在宁可换一条真有内容的结论上来。
 */
function buildDecisionCandidates() {
  const selected = scopedTransactions(state.period);
  const selectedSpend = sum(selected);
  const label = periodLabel();
  const candidates = [];
  const corrections = correctionTransactions();

  if (corrections.length) {
    candidates.push({
      weight: 1000,
      type: "待订正",
      tone: "warn",
      title: `${corrections.length} 笔截图信息不完整`,
      copy: "这些记录已经保留在账本，但暂不计入消费统计。请对照原始截图补全金额、交易时间或商户。",
      actions: [
        { kind: "evidence", text: "逐笔订正", uid: corrections[0].transaction_uid || "" },
      ],
    });
  }

  // — 支出集中：占比之外，还给出和第二名的差额，才知道「集中」到什么程度 —
  const categoryEntries = Object.entries(groupByCategory(selected)).sort((a, b) => b[1].amount - a[1].amount);
  const [top, second] = categoryEntries;
  if (top && selectedSpend > 0) {
    const share = Math.round((top[1].amount / selectedSpend) * 100);
    candidates.push({
      weight: share >= 55 ? 82 : share >= 40 ? 66 : share >= 30 ? 52 : 34,
      type: "支出集中",
      tone: share >= 55 ? "warn" : "normal",
      title: `${categoryLabel(top[0])}占了${periodPhrase("scope")}的 ${share}%`,
      copy: second
        ? `${top[1].count} 笔合计 ${formatMoney(top[1].amount)}，比第二位的${categoryLabel(second[0])}多 ${formatMoney(top[1].amount - second[1].amount)}。`
        : `${top[1].count} 笔合计 ${formatMoney(top[1].amount)}，目前所有消费都落在这一类。`,
      actions: [
        { kind: "ledger", text: `看这 ${top[1].count} 笔`, category: top[0] },
        {
          kind: "ask",
          text: "让 Agent 拆开",
          // 气泡左侧已经有一枚周期标签，问题开头再写一遍「本月」会读成结巴。
          question: `${categoryLabel(top[0])}${periodPhrase("when")}一共 ${top[1].count} 笔、合计 ${formatMoney(top[1].amount)}。帮我逐笔拆一下都花在哪，并指出其中哪几笔属于可以砍掉的开销。`,
        },
      ],
    });
  }

  // — 重复商户：全站只有这里看得到「同一家店来了几次」 —
  const repeat = Object.entries(groupByMerchant(selected))
    .filter(([, info]) => info.count >= 2)
    .sort((a, b) => b[1].count - a[1].count || b[1].amount - a[1].amount)[0];
  if (repeat) {
    const [name, info] = repeat;
    candidates.push({
      weight: info.count >= 4 ? 76 : info.count === 3 ? 62 : 48,
      type: "重复消费",
      tone: info.count >= 4 ? "warn" : "normal",
      title: `${name}${periodPhrase("when")}出现了 ${info.count} 次`,
      copy: `合计 ${formatMoney(info.amount)}，平均每次 ${formatMoney(info.amount / info.count)}${info.latest ? `，最近一次 ${shortChineseDate(info.latest)}` : ""}。`,
      actions: [
        { kind: "ledger", text: `看这 ${info.count} 笔`, category: info.category, merchant: name },
        {
          kind: "ask",
          text: "问问值不值",
          question: `我在「${name}」${periodPhrase("when")}消费了 ${info.count} 次、合计 ${formatMoney(info.amount)}。这个频率算高吗？按这个节奏一个月大概要花多少，有没有更省的替代方案？`,
        },
      ],
    });
  }

  // — 预算推演：首屏给的是「已用多少」，这里给的是「照这样下去会怎样」 —
  const budgetKey = budgetKeyForPeriod();
  const budget = budgetKey ? state.budgets[budgetKey] || 0 : 0;
  if (budget > 0 && selectedSpend > 0 && ["week", "month"].includes(state.period)) {
    const elapsed = elapsedDaysInPeriod();
    const totalDays = periodTotalDays();
    const daily = selectedSpend / elapsed;
    const projected = daily * totalDays;
    const overBy = projected - budget;
    const remainingDays = Math.max(totalDays - elapsed, 0);
    const safeDaily = remainingDays > 0 ? Math.max(budget - selectedSpend, 0) / remainingDays : 0;
    candidates.push({
      weight: overBy > 0 ? 88 : 44,
      type: "预算推演",
      tone: overBy > 0 ? "warn" : "good",
      title: overBy > 0 ? `照这个节奏，${label}会超预算 ${formatMoney(overBy)}` : `照这个节奏，${label}能守住预算`,
      copy: `前 ${elapsed} 天日均 ${formatMoney(daily)}，推到${label}末约 ${formatMoney(projected)}，预算 ${formatMoney(budget)}。${
        remainingDays > 0
          ? overBy > 0
            ? `剩下 ${remainingDays} 天要压到日均 ${formatMoney(safeDaily)} 以内才守得住。`
            : `剩下 ${remainingDays} 天日均还有 ${formatMoney(safeDaily)} 的空间。`
          : ""
      }`,
      actions: [
        { kind: "trend", text: "打开趋势图", mode: budgetKey },
        {
          kind: "ask",
          text: "问怎么收",
          question: `我${label}已经花了 ${formatMoney(selectedSpend)}，预算是 ${formatMoney(budget)}，还剩 ${remainingDays} 天。帮我判断会不会超支，如果要守住预算，具体该从哪几类消费里省。`,
        },
      ],
    });
  }

  // — 单日峰值：哪天花得反常，只有按天聚合才看得出来 —
  if (state.period !== "today") {
    const days = Object.values(groupByDay(selected)).sort((a, b) => b.amount - a.amount);
    const peak = days[0];
    // 均值只按「有消费的天」算，否则周末不花钱会把基准压低，天天都成峰值。
    const activeAverage = days.length ? selectedSpend / days.length : 0;
    if (days.length >= 3 && peak && peak.amount > 0 && peak.amount >= activeAverage * 1.8) {
      candidates.push({
        weight: 64,
        type: "单日峰值",
        tone: "normal",
        title: `${shortChineseDate(peak.date)}一天就花了 ${formatMoney(peak.amount)}`,
        copy: `当天 ${peak.count} 笔，是有消费那几天平均值的 ${(peak.amount / activeAverage).toFixed(1)} 倍。`,
        actions: [
          { kind: "trend", text: "打开趋势图", mode: "day" },
          {
            kind: "ask",
            text: "问那天怎么了",
            question: `${shortChineseDate(peak.date)}这一天我花了 ${formatMoney(peak.amount)}、共 ${peak.count} 笔，明显高于平时。帮我看看那天的钱具体花在哪，是一次性支出还是有异常。`,
          },
        ],
      });
    }
  }

  // — 待核实：解析不确定的账，越早核对越省事 —
  // 除了 OCR 解析置信低，分类环节「勉强给了个答案」的也算：
  // deepseek_low 是模型低分命中，local_industry 是靠行业词猜的，
  // unresolved 是重试到上限也没结论。这些都比「识别中」强，但值得人扫一眼。
  const WEAK_CLASSIFICATION = new Set(["deepseek_low", "local_industry", "unresolved"]);
  // 人工在证据面板核对过就不再提示：解析置信低只说明机器没把握，
  // 人对着截图确认过之后，这笔的不确定性就已经消掉了。
  const unsure = selected
    .filter(
      (tx) =>
        !tx.reviewed_at &&
        (tx.classification_status === "pending" ||
          Number(tx.confidence || 0) < 0.6 ||
          WEAK_CLASSIFICATION.has(tx.classification_source)),
    )
    .sort((a, b) => positiveSpend(b) - positiveSpend(a));
  if (unsure.length) {
    const unsureSpend = unsure.reduce((total, tx) => total + positiveSpend(tx), 0);
    candidates.push({
      weight: 70 + Math.min(unsure.length, 8),
      type: "待核实",
      tone: "warn",
      title: `${unsure.length} 笔的解析结果还不确定`,
      copy: `合计 ${formatMoney(unsureSpend)}，分类或金额可能不准，建议对着原始截图核一遍。`,
      actions: [
        { kind: "evidence", text: "去核对", uid: unsure[0].transaction_uid || "" },
        {
          kind: "ask",
          text: "让 Agent 复核",
          question: `账本里有 ${unsure.length} 笔消费的解析置信度偏低、合计 ${formatMoney(unsureSpend)}。帮我把这几笔列出来，说明每一笔的分类依据，并指出最可能分错的是哪一笔。`,
        },
      ],
    });
  }

  // — 最大单笔：兜底项，同时也是最直接的一条追溯入口 —
  const maxTx = largest(selected);
  if (maxTx) {
    const name = merchantKey(maxTx) || "未知商户";
    const share = selectedSpend > 0 ? Math.round((positiveSpend(maxTx) / selectedSpend) * 100) : 0;
    candidates.push({
      weight: share >= 40 ? 72 : share >= 25 ? 56 : 30,
      type: "最大单笔",
      tone: "normal",
      title: `${name} · ${formatMoney(maxTx.amount)}`,
      copy: `${share > 0 ? `占${periodPhrase("scope")} ${share}%，` : ""}${paymentLabel(maxTx.payment_app)}支付于 ${displayDate(maxTx.paid_at)}。`,
      actions: [
        { kind: "evidence", text: "看原始证据", uid: maxTx.transaction_uid || "" },
        {
          kind: "ask",
          text: "这笔正常吗",
          question: `「${name}」这笔 ${formatMoney(maxTx.amount)} 是${periodPhrase("scope")}里最大的一笔。帮我核对它的分类和消费内容对不对，并判断这类支出多久出现一次算正常。`,
        },
      ],
    });
  }

  // — 兜底：候选不足三条时，至少留一个明确的追问入口，而不是空着半块面板 —
  candidates.push({
    weight: 5,
    type: "样本太少",
    tone: "normal",
    title: `${periodPhrase("when")}记录了 ${selected.length} 笔消费`,
    copy: "样本还不算多，可以让 Agent 直接把这些消费按金额排一遍，先建立一个基线。",
    actions: [
      { kind: "ledger", text: "看全部明细", category: "all" },
      {
        kind: "ask",
        text: "让 Agent 排个序",
        question: `把这个周期里的每一笔消费按金额从高到低列出来，标注商户、分类和支付渠道，最后告诉我哪几笔最值得关注。`,
      },
    ],
  });

  return candidates;
}

function buildDecisionItems() {
  return buildDecisionCandidates()
    .sort((a, b) => b.weight - a.weight)
    .slice(0, 3);
}

const DECISION_ACTION_ICONS = {
  ledger: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 6h14M5 12h14M5 18h9"/></svg>`,
  evidence: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 4.5h8L18 9v10.5H6z"/><path d="M13.5 4.5V9H18"/></svg>`,
  trend: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 16.5 9 11l3.4 3.2L20 6.5"/><path d="M15.4 6.5H20V11"/></svg>`,
  ask: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 15.2a2.3 2.3 0 0 1-2.3 2.3H8.5L4 21V6.3A2.3 2.3 0 0 1 6.3 4h11.4A2.3 2.3 0 0 1 20 6.3z"/></svg>`,
};

function decisionActionButton(action) {
  const attributes = [
    `type="button"`,
    `class="decision-action${action.kind === "ask" ? " is-ask" : ""}"`,
    `data-decision-action="${escapeHtml(action.kind)}"`,
  ];
  if (action.category) attributes.push(`data-category="${escapeHtml(action.category)}"`);
  if (action.merchant) attributes.push(`data-merchant="${escapeHtml(action.merchant)}"`);
  if (action.uid) attributes.push(`data-uid="${escapeHtml(action.uid)}"`);
  if (action.mode) attributes.push(`data-mode="${escapeHtml(action.mode)}"`);
  if (action.question) attributes.push(`data-question="${escapeHtml(action.question)}"`);
  return `<button ${attributes.join(" ")}>${DECISION_ACTION_ICONS[action.kind] || ""}<span>${escapeHtml(action.text)}</span></button>`;
}

/**
 * 「关键观察」的导语。它得念出这一屏真正算出了什么——
 * 读了多少笔、落在几个场景、最后挑中的是哪三条结论。
 * 写死一句「下面是最值得处理的三条」等于没说：换周期、换数据它都不动，
 * 而下面那三张卡是会变的。
 */
function renderSectionNarrative(items) {
  const node = $("coreNarrative");
  const selected = scopedTransactions(state.period);
  const correctionCount = correctionTransactions().length;

  if (!selected.length) {
    node.textContent = correctionCount
      ? `账本已保留 ${correctionCount} 笔待订正记录，补全后才会进入消费分析。`
      : `${periodLabel()}还没有消费记录，换个周期，或者同步一次邮箱账单。`;
    return;
  }

  const scenes = Object.keys(groupByCategory(selected)).length;
  const types = items.map((item) => item.type);
  // 量词跟着下面那块面板的名字走：面板叫「…消费分析」（consumptionAnalysisTitle），
  // 这里就说「N 条消费分析」，指向明确。用「类」会和右侧「支出去向 13 类」撞词义。
  node.textContent = `${periodPhrase("when")} ${selected.length} 笔消费散在 ${scenes} 个场景里，优先处理 ${types.length} 条消费分析：${types.join(" · ")}。`;
}

function renderDecisionFeed() {
  const selected = scopedTransactions(state.period);
  const corrections = correctionTransactions();
  if (!selected.length && !corrections.length) {
    renderSectionNarrative([]);
    $("decisionFeed").innerHTML = emptyState({
      icon: "alert",
      title: `${periodLabel()}还没有消费记录`,
      hint: "换一个周期，或者同步一次邮箱账单，Agent 就会开始给结论。",
    });
    return;
  }

  const items = !selected.length
    ? buildDecisionItems().filter((item) => item.type === "待订正")
    : buildDecisionItems();
  renderSectionNarrative(items);

  $("decisionFeed").innerHTML = items
    .map(
      (item) => `
      <div class="decision-item${item.tone === "warn" ? " warn" : item.tone === "good" ? " good" : ""}">
        <span class="decision-type">${escapeHtml(item.type)}</span>
        <div class="decision-copy">
          <strong>${escapeHtml(item.title)}</strong>
          <span>${escapeHtml(item.copy)}</span>
          ${
            item.actions?.length
              ? `<div class="decision-actions">${item.actions.filter((action) => action.kind !== "evidence" || action.uid).map(decisionActionButton).join("")}</div>`
              : ""
          }
        </div>
      </div>
    `,
    )
    .join("");
}

/**
 * 从分析卡片跳到账本：按分类（可再叠加商户）筛好再滚过去，
 * 让「看这 4 笔」真的只剩那 4 笔，而不是把人扔到一张全量表前面。
 */
function focusLedger({ category = "all", merchant = "" } = {}) {
  state.filter = category || "all";
  state.merchantFocus = merchant || "";
  state.ledgerFilterExpanded = false;
  state.ledgerPage = 1;
  renderFilters();
  renderTransactions();
  // 先让滚动揭示动画把新行的位移清掉，再滚过去：反过来的话滚动落点会被随后的
  // 布局变化带偏，人到了账本却停在半空。
  window.refreshCfoMotion?.({ scope: "ledger" });
  requestAnimationFrame(() => {
    document.getElementById("ledger")?.scrollIntoView({
      behavior: prefersReducedMotion() ? "auto" : "smooth",
      block: "start",
    });
  });
}

/**
 * 从趋势明细格下钻：用户点的是「这段时间」，那就让整个大脑都改看这段时间，
 * 而不是只把账本筛一遍、首屏还写着「本月」。序列里的 end 是半开右界，
 * 退一天转成 customRange 的闭区间末日。
 */
function jumpToTrendPeriod(index) {
  const item = state.activeTrendSeries[index];
  if (!item?.start || !item?.end) return;
  closeModal("trendModal");
  applyCustomRange({ start: item.start, end: addDays(item.end, -1) }, { scrollToLedger: true });
}

/** 从分析卡片直接追问：先把对话滚进视野，再把问题发出去。 */
function askFromInsight(question) {
  if (!question) return;
  document.getElementById("heroChat")?.scrollIntoView({
    behavior: prefersReducedMotion() ? "auto" : "smooth",
    block: "center",
  });
  if (state.chatBusy) {
    showToast("上一个问题还在回答，等它结束再追问。", "info");
    return;
  }
  submitQuestion(question);
}

function renderCategoryStack() {
  const selected = scopedTransactions(state.period);
  const grouped = groupByCategory(selected);
  const entries = Object.entries(grouped).sort((a, b) => b[1].amount - a[1].amount);
  // 分类只统计正向消费，因此占比总额也必须使用分类金额总和，不能混用净支出。
  const total = entries.reduce((acc, [, value]) => acc + value.amount, 0);

  $("categoryStack").innerHTML = entries.length
    ? entries
        .map(([category, value]) => {
          const share = total > 0 ? (value.amount / total) * 100 : 0;
          return `
            <div class="category-row">
              <div class="category-name">
                <span class="legend-dot" style="--seg-color:${categoryColor(category)}" aria-hidden="true"></span>
                <strong>${escapeHtml(categoryLabel(category))}</strong>
              </div>
              <div class="category-value">${escapeHtml(formatMoney(value.amount))}</div>
              <div class="category-track" aria-hidden="true"><span style="--category-ratio:${(clamp(share, 0, 100) / 100).toFixed(4)};--seg-color:${categoryColor(category)}"></span></div>
              <div class="category-sub">${value.count} 笔 · 占 ${Math.round(share)}%</div>
            </div>
          `;
        })
        .join("")
    : ""; // 空态已经由上方的构成条给出，这里不再重复一遍
}

function renderFilters() {
  const referenced = new Set(state.transactions.map((tx) => tx.category || "uncategorized"));
  const primaryCategories = state.categories
    .filter((item) => item.is_enabled && item.is_primary)
    .sort((a, b) => a.primary_order - b.primary_order)
    .map((item) => item.id);
  const otherCategories = state.categories
    .filter((item) => !item.is_primary && (item.is_enabled || referenced.has(item.id)))
    .map((item) => item.id);
  const disabledCategories = otherCategories.filter((category) => !categoryById(category)?.is_enabled);
  const enabledOtherCategories = otherCategories.filter((category) => categoryById(category)?.is_enabled);
  const selectedIsExtra = state.filter !== "all" && otherCategories.includes(state.filter);

  $("filterBar").innerHTML = `
    <div class="filter-strip">
      <div class="filter-strip-scroll">
        ${state.merchantFocus ? `
          <button class="ledger-filter-chip is-merchant" data-clear-merchant type="button" aria-label="取消按商户「${escapeHtml(state.merchantFocus)}」筛选">
            ${escapeHtml(state.merchantFocus)} <span aria-hidden="true">×</span>
          </button>
        ` : ""}
        ${filterButton("all")}
        ${primaryCategories.map((category) => filterButton(category)).join("")}
        ${selectedIsExtra ? filterButton(state.filter, { current: true }) : ""}
      <button class="ledger-filter-more${state.ledgerFilterExpanded ? " active" : ""}" data-filter-action="toggle-more" type="button" aria-expanded="${state.ledgerFilterExpanded ? "true" : "false"}">
        更多分类 <span aria-hidden="true">${state.ledgerFilterExpanded ? "收起" : `+${otherCategories.length}`}</span>
      </button>
      </div>
      <button class="ledger-category-settings" type="button" data-category-manage aria-label="分类管理：新增、改名、图标与常用排序" title="分类管理：新增、改名、图标与常用排序">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 3-.6 2.4-2 .9L4 5.6 2 9l1.8 1.7v2.6L2 15l2 3.4 2.4-.7 2 .9L9 21h6l.6-2.4 2-.9 2.4.7 2-3.4-1.8-1.7v-2.6L22 9l-2-3.4-2.4.7-2-.9L15 3Z"/><circle cx="12" cy="12" r="3"/></svg>
        <span class="ledger-settings-tip" role="tooltip">分类管理 · 名称、图标与排序</span>
      </button>
    </div>
      <div class="filter-popover${state.ledgerFilterExpanded ? " open" : ""}">
        <div class="filter-popover-section">
          <div class="filter-popover-title">常用分类</div>
          <div class="filter-popover-grid">
            ${primaryCategories.map((category) => filterButton(category)).join("")}
            ${primaryCategories.length ? "" : `<span class="filter-popover-empty">尚未设置常用分类</span>`}
          </div>
        </div>
        <div class="filter-popover-section">
          <div class="filter-popover-title">其他分类</div>
          <div class="filter-popover-grid">
            ${enabledOtherCategories.map((category) => filterButton(category)).join("")}
            ${enabledOtherCategories.length ? "" : `<span class="filter-popover-empty">没有其他启用分类</span>`}
          </div>
        </div>
        ${disabledCategories.length ? `
          <div class="filter-popover-section">
            <div class="filter-popover-title">历史分类</div>
            <div class="filter-popover-grid is-disabled-categories">
              ${disabledCategories.map((category) => filterButton(category)).join("")}
            </div>
          </div>
        ` : ""}
      </div>
  `;
}

function renderCorrectionQueue() {
  const host = $("correctionQueue");
  if (!host) return;
  const transactions = correctionTransactions();
  host.hidden = transactions.length === 0;
  if (!transactions.length) {
    host.replaceChildren();
    return;
  }

  host.innerHTML = `
    <div class="correction-queue-head">
      <div>
        <span class="correction-queue-mark" aria-hidden="true">${ICONS.alert}</span>
        <div>
          <strong>${transactions.length} 笔交易待订正</strong>
          <p>它们已被保留，但补全核心信息前不会计入消费统计。</p>
        </div>
      </div>
      <small>所有周期固定显示</small>
    </div>
    <div class="correction-list">
      ${transactions.map((tx) => {
        const missing = transactionCorrectionFields(tx);
        const title = tx.merchant || tx.product || tx.thing || "未识别商户";
        const captured = tx.captured_at || tx.created_at;
        return `
          <button
            class="correction-item"
            type="button"
            data-transaction-uid="${escapeHtml(tx.transaction_uid || "")}"
            aria-label="订正 ${escapeHtml(title)}，缺少${escapeHtml(missing.map((field) => CORRECTION_FIELD_LABELS[field] || field).join("、"))}"
          >
            <span class="correction-item-main">
              <strong>${escapeHtml(title)}</strong>
              <small>${captured ? `同步于 ${escapeHtml(displayDateTime(captured))}` : "同步时间未知"}</small>
            </span>
            <span class="correction-fields" aria-label="待补字段">
              ${missing.map((field) => `<em>${escapeHtml(CORRECTION_FIELD_LABELS[field] || field)}待补</em>`).join("")}
            </span>
            <span class="correction-item-amount">${Number(tx.amount) > 0 ? escapeHtml(formatMoney(tx.amount)) : "金额待补"}</span>
            <span class="correction-item-action">打开订正</span>
          </button>
        `;
      }).join("")}
    </div>
  `;
}

function renderTransactions() {
  renderCorrectionQueue();
  // 时间尺度只有顶栏这一个来源（含自定义区间），账本这里不再叠第二套区间。
  let transactions = scopedTransactions(state.period);
  if (state.filter !== "all") transactions = transactions.filter((tx) => (tx.category || "uncategorized") === state.filter);
  // 商户维度只由分析卡片的「看这 N 笔」写入，筛选栏里以一枚可关闭的胶囊呈现。
  if (state.merchantFocus) transactions = transactions.filter((tx) => merchantKey(tx) === state.merchantFocus);

  const totalPages = Math.max(1, Math.ceil(transactions.length / ledgerPageSize));
  state.ledgerPage = Math.min(Math.max(state.ledgerPage, 1), totalPages);
  const start = (state.ledgerPage - 1) * ledgerPageSize;
  const pageTransactions = transactions.slice(start, start + ledgerPageSize);

  if (!transactions.length) {
    const isFiltered = state.filter !== "all" || Boolean(state.merchantFocus);
    const scopeName = state.merchantFocus || (state.filter !== "all" ? categoryLabel(state.filter) : "");
    const rangeName = periodLabel();
    const body = state.transactions.length
      ? emptyState({
          icon: isFiltered ? "filter" : "empty",
          title: isFiltered ? `${scopeName}在${rangeName}没有记录` : `${periodLabel()}还没有交易`,
          hint: isFiltered ? "换个分类，或者清掉筛选看全部。" : "把账单截图发到绑定邮箱，同步后就会出现在这里。",
          action: isFiltered
            ? `<button class="btn btn-quiet" type="button" data-filter="all">清掉筛选</button>`
            : "",
        })
      : emptyState({
          icon: "mail",
          title: "账本还是空的",
          hint: "从「同步」拉取一次未读账单邮件，Agent 会自动 OCR 并分类。",
          action: `<button class="btn btn-primary" type="button" data-open-modal="syncModal" data-start-sync="true">同步邮箱账单</button>`,
        });
    $("transactionList").innerHTML = `<tr><td colspan="5">${body}</td></tr>`;
    $("ledgerPagination").innerHTML = "";
    return;
  }

  $("transactionList").innerHTML = pageTransactions
    .map((tx) => {
      const title = tx.merchant || tx.product || "未知商户";
      const thing = tx.thing || tx.product || "未识别消费内容";
      const method = tx.payment_method || "未知支付方式";
      const source = `${paymentLabel(tx.payment_app)} · ${method}`;
      const pending = tx.classification_status === "pending";
      const category = tx.category || "uncategorized";
      const isInflow = tx.direction === "inflow";
      return `
        <tr
          class="txn-row"
          role="row"
          data-motion-row
          data-transaction-uid="${escapeHtml(tx.transaction_uid || "")}"
          tabindex="0"
          aria-label="查看 ${escapeHtml(title)} ${escapeHtml(formatMoney(tx.amount))} 的交易证据"
        >
          <td role="cell" class="td-time">${escapeHtml(displayDate(tx.paid_at))}</td>
          <td role="cell" class="td-main">
            <div class="txn-title" title="${escapeHtml(title)}">${escapeHtml(title)}</div>
            <div class="txn-meta" title="${escapeHtml(thing)}">${escapeHtml(thing)}</div>
          </td>
          <td role="cell" class="td-category">
            <span class="txn-chip${pending ? " is-pending" : ""}">
              <span class="txn-category-icon" style="color:${pending ? "var(--amber-8)" : categoryColor(category)}">${categoryIcon(pending ? "circle" : categoryById(category)?.icon_key)}</span>
              <span>${escapeHtml(pending ? "识别中" : categoryLabel(category))}</span>
            </span>
          </td>
          <td role="cell" class="td-source">${escapeHtml(source)}</td>
          <td role="cell" class="td-amount${isInflow ? " is-inflow" : ""}">${escapeHtml(`${isInflow ? "+" : ""}${formatMoney(tx.amount)}`)}</td>
        </tr>
      `;
    })
    .join("");

  $("ledgerPagination").innerHTML = transactions.length > ledgerPageSize
    ? `
      <div class="pagination-summary">共 ${transactions.length} 条 · 第 ${state.ledgerPage} / ${totalPages} 页</div>
      <form class="pagination-jump" data-page-jump-form>
        <label for="ledgerPageJump">跳至</label>
        <input
          id="ledgerPageJump"
          type="number"
          inputmode="numeric"
          min="1"
          max="${totalPages}"
          value="${state.ledgerPage}"
          aria-label="输入页码跳转"
        />
        <span>页</span>
        <button type="submit">跳转</button>
      </form>
      <div class="pagination-actions">
        <button type="button" data-page-action="prev" ${state.ledgerPage <= 1 ? "disabled" : ""}>上一页</button>
        <button type="button" data-page-action="next" ${state.ledgerPage >= totalPages ? "disabled" : ""}>下一页</button>
      </div>
    `
    : "";
}

/* ------------------------------- 对话 ------------------------------- */

function setChatPageLock(locked) {
  const body = document.body;
  if (locked) {
    const scrollbarWidth = Math.max(0, window.innerWidth - document.documentElement.clientWidth);
    body.style.setProperty("--chat-scrollbar-compensation", `${scrollbarWidth}px`);
    body.classList.add("chat-expanded-open");
    return;
  }
  body.classList.remove("chat-expanded-open");
  body.style.removeProperty("--chat-scrollbar-compensation");
}

function restoreChatScrollPosition(position) {
  if (!position) return;
  const root = document.documentElement;
  const previousScrollBehavior = root.style.scrollBehavior;
  root.style.scrollBehavior = "auto";
  window.scrollTo(position.left, position.top);
  root.style.scrollBehavior = previousScrollBehavior;
}

function chatIsAtLatest() {
  const messages = $("chatMessages");
  if (!messages) return true;
  return messages.scrollHeight - messages.scrollTop - messages.clientHeight < 28;
}

function updateChatLatestButton() {
  const button = $("chatLatestButton");
  if (!button) return;
  button.hidden = !state.chatExpanded || chatIsAtLatest();
}

/*
 * 新消息到场时跟到底部。原来是 scrollTop = scrollHeight 的硬跳：气泡还没升起来，
 * 视口已经到位了，看着像画面闪了一下。改成平滑跟随，和气泡的入场同时发生，
 * 两者合起来才是「这句话被送进去了」。连着两次（提问 + 思考气泡）由浏览器自己接管，
 * 后一次会平滑接管前一次。
 */
function followChatToLatest() {
  const messages = $("chatMessages");
  if (!messages) return;
  if (prefersReducedMotion()) {
    messages.scrollTop = messages.scrollHeight;
    return;
  }
  messages.scrollTo({ top: messages.scrollHeight, behavior: "smooth" });
}

function scrollChatToLatest() {
  const messages = $("chatMessages");
  if (!messages) return;
  messages.scrollTo({ top: messages.scrollHeight, behavior: "smooth" });
  window.setTimeout(updateChatLatestButton, 340);
}

function latestAgentAnswer() {
  return [...state.chatHistory].reverse().find((item) => item.role === "assistant")?.content || "";
}

async function copyLastAnswer() {
  const answer = latestAgentAnswer();
  if (!answer) {
    showToast("还没有可以复制的 CFO 回答", "error");
    return;
  }

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(answer);
    } else {
      const textarea = document.createElement("textarea");
      textarea.value = answer;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
    }
    showToast("最近一条 CFO 回答已复制");
  } catch {
    showToast("复制失败，请手动选择回答内容", "error");
  }
}

function prepareChatCollapsePreview(chat, placeholder) {
  const preview = chat.cloneNode(true);
  preview.removeAttribute("id");
  preview.classList.remove("is-expanded", "is-expanded-active", "is-collapsing");
  preview.classList.add("chat-collapse-preview");
  preview.setAttribute("aria-hidden", "true");
  preview.style.removeProperty("transition");
  preview.style.removeProperty("transform");
  preview.style.removeProperty("transform-origin");
  preview.style.removeProperty("opacity");
  preview.querySelector("#copyLastAnswerButton")?.setAttribute("hidden", "");
  preview.querySelector("#closeChatExpandButton")?.setAttribute("hidden", "");
  preview.querySelectorAll("[id]").forEach((node) => node.removeAttribute("id"));
  placeholder.replaceChildren(preview);
  return preview;
}

function openChatExpanded() {
  if (state.chatExpanded) return;
  const chat = $("heroChat");
  const backdrop = $("chatExpandBackdrop");
  const placeholder = $("chatExpandPlaceholder");
  const expandButton = $("expandChatButton");
  const copyButton = $("copyLastAnswerButton");
  const closeButton = $("closeChatExpandButton");
  if (!chat || !backdrop || !placeholder || !copyButton || !closeButton) return;

  state.chatTransitionCancel?.();
  state.chatTransitionCancel = null;
  placeholder.replaceChildren();
  const originRect = chat.getBoundingClientRect();
  state.chatExpanded = true;
  state.chatReturnFocusElement = document.activeElement;
  state.chatReturnScrollPosition = { left: window.scrollX, top: window.scrollY };
  setChatPageLock(true);
  backdrop.hidden = false;
  placeholder.hidden = false;
  placeholder.classList.add("is-visible");
  copyButton.hidden = false;
  closeButton.hidden = false;
  chat.classList.remove("is-collapsing");
  chat.classList.add("is-expanded");
  chat.style.transition = "none";
  chat.style.transformOrigin = "top left";
  chat.style.opacity = "1";
  chat.style.transform = "none";
  chat.style.willChange = "transform, opacity";
  const targetRect = chat.getBoundingClientRect();
  const startScaleX = targetRect.width ? originRect.width / targetRect.width : 1;
  const startScaleY = targetRect.height ? originRect.height / targetRect.height : 1;
  chat.style.transform = `translate3d(${originRect.left - targetRect.left}px, ${originRect.top - targetRect.top}px, 0) scale(${startScaleX}, ${startScaleY})`;
  expandButton?.setAttribute("aria-expanded", "true");
  updateChatLatestButton();

  requestAnimationFrame(() => {
    backdrop.classList.add("is-visible");
    chat.classList.add("is-expanded-active");
    chat.style.transition = "transform var(--motion-chat-enter) var(--ease-out), opacity var(--motion-overlay-enter) var(--ease-out)";
    chat.style.transform = "none";
    closeButton.focus({ preventScroll: true });
  });

  state.chatTransitionCancel = afterTransition(chat, () => {
    if (!state.chatExpanded) return;
    chat.style.transition = "";
    chat.style.transform = "";
    chat.style.transformOrigin = "";
    chat.style.opacity = "";
    chat.style.willChange = "";
    state.chatTransitionCancel = null;
  }, { fallback: 540 });
}

function closeChatExpanded() {
  if (!state.chatExpanded) return;
  const chat = $("heroChat");
  const backdrop = $("chatExpandBackdrop");
  const placeholder = $("chatExpandPlaceholder");
  const expandButton = $("expandChatButton");
  const copyButton = $("copyLastAnswerButton");
  const closeButton = $("closeChatExpandButton");
  if (!chat || !backdrop || !placeholder || !copyButton || !closeButton) return;

  state.chatTransitionCancel?.();
  state.chatTransitionCancel = null;
  placeholder.hidden = false;
  placeholder.classList.add("is-visible");
  const preview = prepareChatCollapsePreview(chat, placeholder);
  const renderedOpacity = getComputedStyle(chat).opacity;
  chat.style.transition = "none";
  chat.style.transform = "none";
  chat.style.opacity = renderedOpacity;
  chat.style.transformOrigin = "";
  chat.style.willChange = "opacity";
  state.chatExpanded = false;
  chat.classList.add("is-collapsing");
  backdrop.classList.remove("is-visible");
  expandButton?.setAttribute("aria-expanded", "false");

  requestAnimationFrame(() => {
    preview.classList.add("is-preview-visible");
    chat.style.transition = "opacity var(--motion-chat-exit) var(--ease-out)";
    chat.style.opacity = "0";
  });

  state.chatTransitionCancel = afterTransition(chat, () => {
    if (state.chatExpanded) return;
    chat.classList.remove("is-expanded", "is-expanded-active", "is-collapsing");
    copyButton.hidden = true;
    closeButton.hidden = true;
    placeholder.replaceChildren();
    placeholder.classList.remove("is-visible");
    placeholder.hidden = true;
    backdrop.hidden = true;
    setChatPageLock(false);
    chat.style.transition = "";
    chat.style.transform = "";
    chat.style.transformOrigin = "";
    chat.style.opacity = "";
    chat.style.willChange = "";
    if (state.chatReturnFocusElement instanceof HTMLElement) {
      state.chatReturnFocusElement.focus({ preventScroll: true });
    } else {
      expandButton?.focus({ preventScroll: true });
    }
    const returnScrollPosition = state.chatReturnScrollPosition;
    if (returnScrollPosition) {
      restoreChatScrollPosition(returnScrollPosition);
      requestAnimationFrame(() => {
        restoreChatScrollPosition(returnScrollPosition);
      });
    }
    state.chatReturnFocusElement = null;
    state.chatReturnScrollPosition = null;
    state.chatTransitionCancel = null;
  }, { property: "opacity", fallback: 360 });
}

function messageUsesDocumentLayout(text) {
  const content = String(text || "");
  return (
    content.length > 180 ||
    /(^|\n)\s*(#{1,3}\s|[-*]\s|\d+\.\s|>\s)/.test(content) ||
    /\|.+\|/.test(content)
  );
}

function addMessage(role, text, options = {}) {
  const shouldSave = options.save !== false;
  const container = $("chatMessages");
  const node = document.createElement("div");
  node.className = `message ${role}`;
  if (options.reset) node.classList.add("reset-message");
  if (role === "agent" && !options.thinking && messageUsesDocumentLayout(text)) {
    node.classList.add("document-message");
  }
  node.setAttribute("aria-label", role === "user" ? "提问者消息" : "CFO Agent 回答");

  const avatar = document.createElement("img");
  avatar.className = "message-avatar";
  avatar.src = role === "user" ? chatAvatarAssets.user : chatAvatarAssets.agent;
  avatar.alt = role === "user" ? "提问者像素头像" : "CFO Agent 像素头像";
  avatar.width = 36;
  avatar.height = 36;
  avatar.loading = "lazy";
  avatar.decoding = "async";

  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  if (options.thinking) {
    node.classList.add("thinking-message");
    bubble.innerHTML = `<span class="typing-dots" aria-hidden="true"><i></i><i></i><i></i></span><span>${escapeHtml(text)}</span>`;
  } else {
    if (options.periodTag) {
      const chip = document.createElement("span");
      chip.className = "period-chip";
      chip.textContent = options.periodTag;
      bubble.appendChild(chip);
    }
    const body = document.createElement("div");
    body.className = "message-body";
    setMessageContent(body, role, text, options);
    bubble.appendChild(body);
  }
  node.append(avatar, bubble);
  container.appendChild(node);
  followChatToLatest();
  updateChatLatestButton();
  if (shouldSave && (role === "user" || role === "agent")) {
    state.chatHistory.push({
      role: role === "agent" ? "assistant" : "user",
      content: text,
    });
    state.chatHistory = state.chatHistory.slice(-12);
  }
  return node;
}

function setChatBusy(busy) {
  state.chatBusy = busy;
  const button = document.querySelector(".chat-send");
  const clearButton = $("clearChatButton");
  const input = $("chatInput");
  if (button) {
    button.disabled = busy;
    const text = button.querySelector(".chat-send-text");
    if (text) text.textContent = busy ? button.dataset.labelBusy : button.dataset.labelIdle;
  }
  if (input) input.setAttribute("aria-busy", busy ? "true" : "false");
  if (clearButton) clearButton.disabled = busy;
  document.querySelectorAll(".quick-prompts button").forEach((node) => {
    node.disabled = busy;
  });
}

function clearChatSession() {
  if (state.chatBusy) return;
  state.chatHistory = [];
  $("chatMessages").innerHTML = "";
  $("headerSummary").textContent = "会话已清空 · 等待你的下一次提问";
  const resetMessage = addMessage(
    "agent",
    "会话面板已清空，我们再来聊点什么呢。",
    { save: false, reset: true },
  );
  resetMessage.setAttribute("aria-label", "CFO Agent 会话状态提示");
  $("chatInput").value = "";
  updateChatLatestButton();
  $("chatInput").focus();
  showToast("会话已清空，随时可以继续提问");
}

async function askCfoAgent(question, history, { scoped = true } = {}) {
  // 不跟随顶栏时段时按「全部」发：服务端注入的就是整本账的汇总，
  // 时间范围完全交给问题文字，模型不会再被一个没人要求的「本周」带偏。
  const period = scoped ? state.period : "all";
  const response = await fetch("./api/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      message: question,
      period,
      // 自定义区间下多带一对闭区间日期，服务端据此算权威汇总，
      // 否则 Agent 会拿「全部」的口径回答一个只问某段时间的问题。
      ...(period === "custom" && state.customRange
        ? { start_date: dateKey(state.customRange.start), end_date: dateKey(state.customRange.end) }
        : {}),
      history,
      budgets: state.budgets,
    }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.answer || `请求失败：HTTP ${response.status}`);
  return data.answer || "模型没有返回可展示的内容，请再问一次。";
}

/*
 * scoped=false 的提问不吃顶栏时段：问题文字自己说了要问哪一段（或者压根不限时段），
 * 再给气泡贴一个「本周」既没依据也会误导——上面那句话和下面那段回答会对不上。
 */
async function submitQuestion(question, { scoped = true } = {}) {
  if (state.chatBusy) return;
  setChatBusy(true);
  const priorHistory = [...state.chatHistory];
  addMessage("user", question, scoped ? { periodTag: periodLabel(state.period) } : {});
  const thinkingNode = addMessage("agent", "正在读取账本并生成回答", { save: false, thinking: true });
  try {
    const answer = await askCfoAgent(question, priorHistory, { scoped });
    thinkingNode.classList.remove("thinking-message");
    thinkingNode.classList.toggle("document-message", messageUsesDocumentLayout(answer));
    const bubble = thinkingNode.querySelector(".message-bubble");
    bubble.innerHTML = "";
    const body = document.createElement("div");
    body.className = "message-body";
    bubble.appendChild(body);
    setMessageContent(body, "agent", answer, { split: true });
    state.chatHistory.push({ role: "assistant", content: answer });
    state.chatHistory = state.chatHistory.slice(-12);
  } catch (error) {
    const fallback = `没能拿到回答：${error.message}`;
    thinkingNode.classList.remove("thinking-message");
    thinkingNode.classList.remove("document-message");
    thinkingNode.classList.add("error-message");
    const bubble = thinkingNode.querySelector(".message-bubble");
    bubble.innerHTML = "";
    const body = document.createElement("div");
    body.className = "message-body";
    bubble.appendChild(body);
    setMessageContent(body, "agent", fallback);
    state.chatHistory.push({ role: "assistant", content: fallback });
    state.chatHistory = state.chatHistory.slice(-12);
  } finally {
    setChatBusy(false);
    followChatToLatest();
    updateChatLatestButton();
  }
}

/* ------------------------------- 邮箱同步 ------------------------------- */

function setSyncModalState(kind, title, meta) {
  const card = $("syncStateCard");
  card.className = `sync-state-card ${kind || ""}`.trim();
  $("syncStatusLabel").textContent = kind === "running" ? "同步中" : kind === "success" ? "同步完成" : kind === "error" ? "同步失败" : "准备同步";
  $("syncStatusTitle").textContent = title;
  $("syncStatusMeta").textContent = meta;
}

function renderSyncMetrics(payload = {}) {
  $("syncCandidateCount").textContent = payload.candidate_count ?? "--";
  $("syncMatchedCount").textContent = payload.matched_messages ?? "--";
  $("syncAttachmentCount").textContent = payload.processed_attachments ?? "--";
  $("syncNewCount").textContent = payload.new_transactions ?? "--";
  $("syncCorrectionCount").textContent = payload.new_correction_count ?? "--";
}

function renderSyncItems(items = []) {
  $("syncItemList").innerHTML = items.length
    ? items
        .map(
          (item) => `
          <button class="sync-item${item.analysis_eligible === false ? " needs-correction" : ""}" type="button" data-transaction-uid="${escapeHtml(item.transaction_uid || "")}" ${item.transaction_uid ? "" : "disabled"}>
            <div>
              <div class="sync-item-title">${escapeHtml(item.merchant || "未知商户")}</div>
              <div class="sync-item-meta">${escapeHtml(item.paid_at ? displayDate(item.paid_at) : "交易时间待补")} · ${escapeHtml(item.transaction_uid || item.uid || "未生成交易号")}</div>
            </div>
            <div>
              <div class="sync-item-amount">${Number(item.amount) > 0 ? escapeHtml(formatMoney(item.amount)) : "金额待补"}</div>
              <div class="sync-item-category">${escapeHtml(item.analysis_eligible === false ? "待订正 · 打开处理" : "完整入账")}</div>
            </div>
          </button>
        `,
        )
        .join("")
    : emptyState({ icon: "mail", title: "本次没有新的账单附件", hint: "所有未读账单邮件都已经处理过了。" });
}

function resetSyncModal() {
  setSyncModalState("idle", "等待开始", "将扫描未读账单邮件，成功处理后自动标记已读。");
  renderSyncMetrics();
  $("syncFinishedAt").textContent = "未开始";
  $("syncItemList").innerHTML = emptyState({ icon: "mail", title: "还没有开始同步", hint: "点击下方「开始同步」连接邮箱。" });
}

async function syncMailData() {
  if (state.syncBusy) return;
  state.syncBusy = true;
  $("startSyncButton").disabled = true;
  $("openSyncModal").disabled = true;
  $("startSyncButton").textContent = "同步中…";
  setSyncModalState("running", "正在连接邮箱并扫描未读账单", "同步期间请保持当前 Web 服务运行。");
  renderSyncMetrics({ candidate_count: "--", matched_messages: "--", processed_attachments: "--", new_transactions: "--", new_correction_count: "--" });
  $("syncFinishedAt").textContent = "进行中";
  $("syncItemList").innerHTML = `
    <div class="empty-state">
      <span class="skeleton skeleton-row" style="width:70%"></span>
      <span class="skeleton skeleton-row" style="width:48%"></span>
      <span>正在读取邮箱与 OCR 账单截图…</span>
    </div>
  `;

  try {
    const response = await fetch("./api/sync-mail", { method: "POST" });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.answer || `同步请求失败：HTTP ${response.status}`);
    }

    await Promise.all([loadSnapshot(), reloadCategories()]);
    renderAll();
    if (!$("trendModal").hidden) renderTrendModal();
    window.refreshCfoMotion?.();

    renderSyncMetrics(payload);
    renderSyncItems(payload.items || []);
    $("syncFinishedAt").textContent = payload.finished_at ? displayDateTime(payload.finished_at) : "刚刚";
    const title = payload.new_transactions > 0
      ? payload.new_correction_count > 0
        ? `已收录 ${payload.new_transactions} 笔，其中 ${payload.new_correction_count} 笔待订正`
        : `已收录 ${payload.new_transactions} 笔新交易`
      : "没有发现新的未读账单";
    const meta = `扫描 ${payload.candidate_count} 封候选邮件，命中 ${payload.matched_messages} 封，处理 ${payload.processed_attachments} 个附件，用时 ${payload.duration_seconds}s。`;
    setSyncModalState("success", title, meta);
    acknowledgeAgentStatus();
    if (payload.new_transactions > 0) {
      showToast(payload.new_correction_count > 0
        ? `已收录 ${payload.new_transactions} 笔，${payload.new_correction_count} 笔待订正`
        : `同步完成，新增 ${payload.new_transactions} 笔交易`);
    }
    refreshPendingClassifications();
  } catch (error) {
    renderSyncMetrics({ candidate_count: 0, matched_messages: 0, processed_attachments: 0, new_transactions: 0, new_correction_count: 0 });
    $("syncFinishedAt").textContent = "失败";
    $("syncItemList").innerHTML = emptyState({ icon: "alert", title: "同步中断", hint: error.message });
    setSyncModalState("error", "邮箱同步没有完成", error.message);
    showToast("邮箱同步失败，详情见弹窗", "error");
  } finally {
    state.syncBusy = false;
    $("startSyncButton").disabled = false;
    $("openSyncModal").disabled = false;
    $("startSyncButton").textContent = "重新同步";
  }
}

async function refreshPendingClassifications(maxAttempts = 10) {
  for (let attempt = 0; attempt < maxAttempts && state.classificationPendingCount > 0; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 1500));
    await Promise.all([loadSnapshot(), reloadCategories()]);
    renderAll();
    if (!$("trendModal").hidden) renderTrendModal();
  }
}

function renderAll() {
  // 快捷提问的文案吃当前作用域：「试试问」要按新数据重抽，「我的」里跟随时段的那些
  // 也要换时间状语。（旧的 AI 推荐挂在 boot 上，同步完邮件不刷新页面就不会更新。）
  renderPromptRail();
  renderHeader();
  renderMetrics();
  renderHeroBudget();
  renderHeroSpark();
  renderComposition();
  renderDecisionFeed();
  renderCategoryStack();
  renderFilters();
  renderTransactions();
}

/* ------------------------------- 导航 ------------------------------- */

function setActiveNav(sectionId) {
  document.querySelectorAll("[data-nav-section]").forEach((item) => {
    const active = item.dataset.navSection === sectionId;
    item.classList.toggle("is-active", active);
    item.classList.toggle("active", active);
    if (active) {
      item.setAttribute("aria-current", "location");
    } else {
      item.removeAttribute("aria-current");
    }
  });
}

function syncNavWithScroll() {
  const sections = ["chat", "signals", "ledger"]
    .map((id) => ({ id, element: $(id) }))
    .filter((item) => item.element);
  if (!sections.length) return;

  const railHeight = document.querySelector(".rail")?.getBoundingClientRect().height || 0;
  const anchorY = railHeight + Math.min(window.innerHeight * 0.42, 360);
  let current = sections[0];

  for (const section of sections) {
    if (section.element.getBoundingClientRect().top <= anchorY) {
      current = section;
    }
  }

  setActiveNav(current.id);
}

function wireScrollSpy() {
  let ticking = false;
  const update = () => {
    ticking = false;
    syncNavWithScroll();
    document.body.classList.toggle("is-scrolled", window.scrollY > 8);
  };
  const requestUpdate = () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(update);
  };

  window.addEventListener("scroll", requestUpdate, { passive: true });
  window.addEventListener("resize", requestUpdate);
  requestUpdate();
}

/* ------------------------------- 周期控件 ------------------------------- */

function periodButtons() {
  return Array.from(document.querySelectorAll(".period-btn"));
}

function movePeriodThumb() {
  const control = document.querySelector(".period-control");
  const thumb = control?.querySelector(".period-thumb");
  const active = control?.querySelector(".period-btn.active");
  if (!control || !thumb || !active) return;
  const controlRect = control.getBoundingClientRect();
  const activeRect = active.getBoundingClientRect();
  // 滑块静态位置是 left:3px（= padding），所以位移要减掉边框和这 3px。
  // 窄屏下控件自己会横向滚动，滑块跟着内容走，位移要换算回内容坐标系。
  const offset = activeRect.left - controlRect.left + control.scrollLeft - control.clientLeft - 3;
  thumb.style.width = `${activeRect.width}px`;
  thumb.style.transform = `translateX(${offset}px)`;
}

/** 窄屏五段放不下时控件会横向滚动，别让选中的那段停在视野外。 */
function scrollActivePeriodIntoView() {
  const control = document.querySelector(".period-control");
  const active = control?.querySelector(".period-btn.active");
  if (!control || !active) return;
  const overflow = control.scrollWidth - control.clientWidth;
  if (overflow <= 0) return;
  const target = active.offsetLeft - (control.clientWidth - active.offsetWidth) / 2;
  control.scrollTo({
    left: clamp(target, 0, overflow),
    behavior: prefersReducedMotion() ? "auto" : "smooth",
  });
}

/** 把 state.period 画到分段控件上：选中态、自定义段的文字、滑块、清除按钮。 */
function syncPeriodButtons() {
  const buttons = periodButtons();
  if (!buttons.length) return;
  const custom = $("customPeriodBtn");
  if (custom) {
    const isCustom = state.period === "custom";
    const label = custom.querySelector(".period-btn-label");
    if (label) label.textContent = isCustom ? customRangeLabel(state.customRange, { short: true }) : "自定义";
    custom.classList.toggle("has-range", isCustom);
  }
  buttons.forEach((item) => {
    const active = item.dataset.period === state.period;
    item.classList.toggle("active", active);
    item.setAttribute("aria-checked", active ? "true" : "false");
    item.tabIndex = active ? 0 : -1;
  });
  // 任何一段都没命中时（理论上不会），至少留一个能 Tab 进来的入口。
  if (!buttons.some((item) => item.tabIndex === 0)) buttons[0].tabIndex = 0;
  const clear = $("periodClear");
  if (clear) clear.hidden = state.period !== "custom";
  movePeriodThumb();
  scrollActivePeriodIntoView();
}

function selectPeriod(button, options = {}) {
  if (!button) return;
  // 「自定义」这一段是个开关，不是一个现成的周期：先让人把区间说出来。
  if (button.dataset.period === "custom") {
    openRangePicker();
    return;
  }
  state.period = button.dataset.period;
  state.lastPresetPeriod = state.period;
  // 换周期后旧商户可能一笔都没有，留着只会得到一张空表。
  state.merchantFocus = "";
  state.ledgerPage = 1;
  syncPeriodButtons();
  updateQuickPrompts();
  renderAll();
  if (options.focus) button.focus();
  window.refreshCfoMotion?.({ scope: "global" });
}

/** 落定一个自定义区间：它和四个预设档一样，是全站唯一的时间尺度。 */
function applyCustomRange(range, options = {}) {
  const start = startOfDay(range?.start);
  const end = startOfDay(range?.end ?? range?.start);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return;
  state.customRange = end < start ? { start: end, end: start } : { start, end };
  state.period = "custom";
  state.merchantFocus = "";
  state.ledgerPage = 1;
  syncPeriodButtons();
  updateQuickPrompts();
  renderAll();
  window.refreshCfoMotion?.({ scope: "global" });
  if (!options.scrollToLedger) return;
  requestAnimationFrame(() => {
    document.getElementById("ledger")?.scrollIntoView({
      behavior: prefersReducedMotion() ? "auto" : "smooth",
      block: "start",
    });
  });
}

/** 清掉自定义区间，回到上一次用过的预设档。 */
function clearCustomRange(options = {}) {
  const fallback = state.lastPresetPeriod || "today";
  const target = periodButtons().find((item) => item.dataset.period === fallback);
  selectPeriod(target || periodButtons()[0], options);
}

/* --------------------------- 自定义区间选择面板 --------------------------- */

const RANGE_PRESETS = [
  { id: "last7", label: "最近 7 天" },
  { id: "last30", label: "最近 30 天" },
  { id: "last_month", label: "上月" },
  { id: "year", label: "今年" },
  { id: "last_year", label: "去年" },
];

const RANGE_WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];

/** 预设区间一律返回闭区间 { start, end }。 */
function presetRange(id) {
  const today = startOfDay(getAnchorDate());
  const thisMonth = new Date(today.getFullYear(), today.getMonth(), 1);
  if (id === "last7") return { start: addDays(today, -6), end: today };
  if (id === "last30") return { start: addDays(today, -29), end: today };
  if (id === "last_month") return { start: addMonths(thisMonth, -1), end: addDays(thisMonth, -1) };
  if (id === "year") return { start: new Date(today.getFullYear(), 0, 1), end: today };
  if (id === "last_year") {
    return { start: new Date(today.getFullYear() - 1, 0, 1), end: new Date(today.getFullYear() - 1, 11, 31) };
  }
  return null;
}

function dateFromKey(key) {
  const [year, month, day] = String(key).split("-").map(Number);
  return new Date(year, month - 1, day);
}

/** 桌面并排两个月，窄屏一次一个月。 */
function isDualMonthView() {
  return window.matchMedia("(min-width: 721px)").matches;
}

/** 哪天有交易——日期格下面那个点就靠它，选区间时不用盲猜哪段有数据。 */
function transactionDayMap() {
  const counts = new Map();
  analysisTransactions().forEach((tx) => {
    const paidAt = parseDate(tx.paid_at);
    if (Number.isNaN(paidAt.getTime())) return;
    const key = dateKey(paidAt);
    counts.set(key, (counts.get(key) || 0) + 1);
  });
  return counts;
}

/** 草稿态可能只点了起点，或者终点在起点之前，这里统一成规规矩矩的闭区间。 */
/*
 * 两份草稿必须分开：
 * - committed（默认）是「点出来」的那份，按下应用落地的就是它；
 * - preview 才把悬停那天算进去，只用来画日历和给个预读数。
 * 混成一份的后果是预览会变成应用值：预览一消失（手指移开、指针离开网格），
 * 按下去的区间就缩回起点那一天。
 */
function normalizedDraft({ preview = false } = {}) {
  const draft = state.rangeDraft;
  if (!draft?.start) return null;
  const hovered = preview && state.rangeHoverKey ? dateFromKey(state.rangeHoverKey) : null;
  const end = draft.end || hovered || draft.start;
  return end < draft.start ? { start: end, end: draft.start } : { start: draft.start, end };
}

/** 可见的月份不能越过当月：未来没有账可看。 */
function clampRangeCursor() {
  const today = startOfDay(getAnchorDate());
  const thisMonth = new Date(today.getFullYear(), today.getMonth(), 1);
  const lastVisible = isDualMonthView() ? addMonths(state.rangeCursor, 1) : state.rangeCursor;
  if (lastVisible > thisMonth) {
    state.rangeCursor = isDualMonthView() ? addMonths(thisMonth, -1) : thisMonth;
  }
}

function renderMonthGrid(monthStart, dayCounts) {
  const today = startOfDay(getAnchorDate());
  const monthEnd = addMonths(monthStart, 1);
  const first = startOfWeek(monthStart);
  const weeks = Math.round((startOfWeek(addDays(monthEnd, -1)) - first) / (7 * 86400000)) + 1;

  const cells = [];
  for (let index = 0; index < weeks * 7; index += 1) {
    const day = addDays(first, index);
    // 邻月的日子留白而不是灰着显示：两个月的网格能对齐，也不会让人误点到隔壁月份。
    if (day < monthStart || day >= monthEnd) {
      cells.push(`<span class="range-day is-outside" aria-hidden="true"></span>`);
      continue;
    }
    const key = dateKey(day);
    const count = dayCounts.get(key) || 0;
    const classes = ["range-day"];
    if (count) classes.push("has-data");
    if (sameDay(day, today)) classes.push("is-today");
    cells.push(`
      <button
        class="${classes.join(" ")}"
        type="button"
        data-range-day="${key}"
        tabindex="-1"
        ${day > today ? "disabled" : ""}
        aria-label="${day.getFullYear()}年${day.getMonth() + 1}月${day.getDate()}日${count ? `，${count} 笔消费` : "，没有消费"}"
      >${day.getDate()}</button>
    `);
  }

  return `
    <div class="range-month">
      <div class="range-weekdays" aria-hidden="true">${RANGE_WEEKDAYS.map((day) => `<span>${day}</span>`).join("")}</div>
      <div class="range-grid">${cells.join("")}</div>
    </div>
  `;
}

function renderRangeMonths() {
  const host = $("rangeMonths");
  const titles = $("rangeMonthTitles");
  if (!host || !titles) return;
  const months = isDualMonthView() ? [state.rangeCursor, addMonths(state.rangeCursor, 1)] : [state.rangeCursor];
  const dayCounts = transactionDayMap();
  titles.innerHTML = months
    .map((month) => `<span>${month.getFullYear()}年${month.getMonth() + 1}月</span>`)
    .join("");
  host.innerHTML = months.map((month) => renderMonthGrid(month, dayCounts)).join("");
}

/** 选区只改 class，不重建网格——鼠标划过预览时才不会闪。 */
function paintRangeSelection() {
  const draft = normalizedDraft({ preview: true });
  const cells = Array.from(document.querySelectorAll("#rangeMonths [data-range-day]"));
  if (!draft) {
    // 取消选中之后得把上一次的高亮抹掉，否则日历上还留着一段「选中的样子」。
    cells.forEach((cell) => {
      cell.classList.remove("is-in-range", "is-start", "is-end", "is-single", "is-preview");
      cell.tabIndex = -1;
    });
    const first = cells.find((cell) => !cell.disabled);
    if (first) first.tabIndex = 0;
    return;
  }
  const pending = !state.rangeDraft.end;
  let hasTabStop = false;
  cells.forEach((cell) => {
    const day = dateFromKey(cell.dataset.rangeDay);
    const inRange = day >= draft.start && day <= draft.end;
    cell.classList.toggle("is-in-range", inRange);
    cell.classList.toggle("is-start", sameDay(day, draft.start));
    cell.classList.toggle("is-end", sameDay(day, draft.end));
    cell.classList.toggle("is-single", inRange && sameDay(draft.start, draft.end));
    cell.classList.toggle("is-preview", inRange && pending);
    const focused = cell.dataset.rangeDay === state.rangeFocusKey && !cell.disabled;
    cell.tabIndex = focused ? 0 : -1;
    if (focused) hasTabStop = true;
  });
  // 焦点日不在当前显示的月份里时，别让整块网格 Tab 不进来。
  if (!hasTabStop) {
    const fallback = cells.find((cell) => !cell.disabled);
    if (fallback) fallback.tabIndex = 0;
  }
}

/*
 * 「应用」这枚按钮必须自己说清楚这一下会应用什么。原来它永远只写「应用」：
 * 只点了起点（第二下没点上、或者又点回同一天）时，按下去会静默变成一天的区间——
 * 人以为选的是 9/1–9/4，结果只看到 9/1。现在按钮上写的就是实际会生效的那段。
 */
function renderRangeSummary() {
  const node = $("rangeSummary");
  const apply = $("rangeApply");
  const committed = normalizedDraft();
  const draft = normalizedDraft({ preview: true });
  if (!node) return;

  if (!draft) {
    node.innerHTML = `
      <b>还没选</b>
      <span>点日历里的一天定起点，或者从上面挑一段。</span>
    `;
    if (apply) {
      apply.disabled = true;
      apply.textContent = "应用";
    }
    return;
  }

  const bounds = { start: draft.start, end: addDays(draft.end, 1) };
  const transactions = transactionsBetween(bounds.start, bounds.end);
  const days = Math.max(1, Math.round((bounds.end - bounds.start) / 86400000));

  // 按钮说的是 committed：悬停预览再长，按下去也只会落地已经点出来的那段。
  if (apply) {
    const committedDays = Math.max(
      1,
      Math.round((addDays(committed.end, 1) - committed.start) / 86400000),
    );
    apply.disabled = false;
    apply.textContent = committedDays === 1 ? "只应用这一天" : `应用这 ${committedDays} 天`;
  }

  if (!state.rangeDraft.end) {
    node.innerHTML = `
      <b>${escapeHtml(customRangeLabel(draft))}</b>
      <span>${state.rangeHoverKey ? `预览 ${days} 天 · 再点一下定终点` : "还差终点：再点一天，或者按「只应用这一天」。"}</span>
    `;
    return;
  }
  node.innerHTML = `
    <b>${escapeHtml(customRangeLabel(draft))}</b>
    <span>${days} 天 · ${transactions.length} 笔 · ${escapeHtml(formatMoney(sum(transactions)))}</span>
  `;
}

function renderRangePresets() {
  const host = $("rangePresets");
  if (!host) return;
  const draft = state.rangeDraft?.end ? normalizedDraft() : null;
  host.innerHTML = RANGE_PRESETS.map((preset) => {
    const range = presetRange(preset.id);
    const active = Boolean(draft && range && sameDay(draft.start, range.start) && sameDay(draft.end, range.end));
    return `
      <button class="range-preset${active ? " active" : ""}" type="button" data-range-preset="${preset.id}" aria-pressed="${active}">
        ${escapeHtml(preset.label)}
      </button>
    `;
  }).join("");
}

function updateRangeNavState() {
  const today = startOfDay(getAnchorDate());
  const thisMonth = new Date(today.getFullYear(), today.getMonth(), 1);
  const lastVisible = isDualMonthView() ? addMonths(state.rangeCursor, 1) : state.rangeCursor;
  const next = $("rangeNextMonth");
  if (next) next.disabled = lastVisible >= thisMonth;
}

/*
 * 面板锚在 rail 底边下方。rail 在 1080px 以下会变成两行，
 * 用写死的 --rail-h 会被它盖住，所以每次渲染都按实测高度写一遍。
 */
function syncRangeAnchor() {
  const rail = document.querySelector(".rail");
  if (!rail) return;
  const bottom = Math.round(rail.getBoundingClientRect().bottom + 8);
  document.documentElement.style.setProperty("--range-anchor-top", `${bottom}px`);
}

function renderRangePicker() {
  syncRangeAnchor();
  clampRangeCursor();
  renderRangePresets();
  renderRangeMonths();
  paintRangeSelection();
  renderRangeSummary();
  updateRangeNavState();
}

/*
 * 日历该从哪个月排起。双月视图从起点排，起点和终点通常一屏都看得到；
 * 窄屏一次只画一个月，再从起点排就会把人扔在上个月——默认区间是「最近 30 天」，
 * 起点常常在上个月，于是这个月的日子一格都看不见，得先发现翻页箭头才能往下走。
 * 更糟的是选到一半被弹回上个月：第二下点不到想点的那天，最后应用出去的就只剩起点
 * 那一天。窄屏一律从靠近今天的那一头排起。
 */
function rangeAnchorMonth(range) {
  const anchor = (isDualMonthView() ? range.start : range.end || range.start) || range.start;
  return new Date(anchor.getFullYear(), anchor.getMonth(), 1);
}

function openRangePicker() {
  const base = state.customRange || presetRange("last30");
  state.rangeDraft = { start: base.start, end: base.end };
  state.rangeHoverKey = null;
  state.rangeFocusKey = dateKey(base.start);
  state.rangeCursor = rangeAnchorMonth(base);
  $("customPeriodBtn")?.setAttribute("aria-expanded", "true");
  renderRangePicker();
  openModal("rangeModal");
}

function pickRangeDay(key) {
  const day = dateFromKey(key);
  const draft = state.rangeDraft;
  state.rangeFocusKey = key;
  state.rangeHoverKey = null;
  // 已经有完整区间了就重开一轮；否则这一下补的是终点。
  if (!draft?.start || draft.end) state.rangeDraft = { start: day, end: null };
  else if (day < draft.start) state.rangeDraft = { start: day, end: draft.start };
  else state.rangeDraft = { start: draft.start, end: day };
  renderRangePresets();
  paintRangeSelection();
  renderRangeSummary();
}

function shiftRangeCursor(months) {
  state.rangeCursor = addMonths(state.rangeCursor, months);
  renderRangePicker();
}

function focusRangeDay(key) {
  const cell = document.querySelector(`#rangeMonths [data-range-day="${key}"]`);
  if (cell && !cell.disabled) cell.focus();
}

/** 让某一天所在的月份进入视野，方向键才能一路走出当前显示的月份。 */
function ensureRangeDayVisible(day) {
  const monthStart = new Date(day.getFullYear(), day.getMonth(), 1);
  const lastVisible = isDualMonthView() ? addMonths(state.rangeCursor, 1) : state.rangeCursor;
  if (monthStart < state.rangeCursor) state.rangeCursor = monthStart;
  else if (monthStart > lastVisible) {
    state.rangeCursor = isDualMonthView() ? addMonths(monthStart, -1) : monthStart;
  }
}

function moveRangeFocus(step, { unit = "day" } = {}) {
  const today = startOfDay(getAnchorDate());
  const current = state.rangeFocusKey ? dateFromKey(state.rangeFocusKey) : normalizedDraft()?.start;
  if (!current) return;
  let next =
    unit === "month"
      ? new Date(current.getFullYear(), current.getMonth() + step, current.getDate())
      : addDays(current, step);
  if (next > today) next = today;
  state.rangeFocusKey = dateKey(next);
  ensureRangeDayVisible(next);
  renderRangePicker();
  focusRangeDay(state.rangeFocusKey);
}

function handleRangeGridKeydown(event) {
  const moves = {
    ArrowLeft: [-1, "day"],
    ArrowRight: [1, "day"],
    ArrowUp: [-7, "day"],
    ArrowDown: [7, "day"],
    PageUp: [-1, "month"],
    PageDown: [1, "month"],
  };
  const move = moves[event.key];
  if (move) {
    event.preventDefault();
    moveRangeFocus(move[0], { unit: move[1] });
    return;
  }
  if (event.key === "Home" || event.key === "End") {
    const current = state.rangeFocusKey ? dateFromKey(state.rangeFocusKey) : null;
    if (!current) return;
    event.preventDefault();
    const weekStart = startOfWeek(current);
    moveRangeFocus(
      Math.round(((event.key === "Home" ? weekStart : addDays(weekStart, 6)) - current) / 86400000),
    );
  }
}

/* ------------------------------- 事件 ------------------------------- */

function wireInteractions() {
  window.addEventListener("cfo:open-evidence", (event) => {
    if (event.detail?.uid) openEvidence(event.detail.uid);
  });

  // 顶栏已经表达过关注哪个时间尺度，弹窗别把这个上下文丢了。
  // （「分析」信号卡的深链自己指定刻度，不走这里。）
  const openTrendForPeriod = () => {
    state.trendMode = trendModeForPeriod();
    openModal("trendModal");
  };
  $("openTrendModal").addEventListener("click", openTrendForPeriod);
  $("heroSpark").addEventListener("click", () => {
    if (state.period === "all") {
      openModal("profileReportModal");
      return;
    }
    openTrendForPeriod();
  });
  $("openBudgetSettings").addEventListener("click", () => openModal("budgetModal"));

  $("openSyncModal").addEventListener("click", () => {
    openModal("syncModal");
    syncMailData();
  });

  $("startSyncButton").addEventListener("click", () => syncMailData());
  $("clearChatButton").addEventListener("click", clearChatSession);
  $("expandChatButton").addEventListener("click", openChatExpanded);
  $("closeChatExpandButton").addEventListener("click", closeChatExpanded);
  $("copyLastAnswerButton").addEventListener("click", copyLastAnswer);
  $("chatLatestButton").addEventListener("click", scrollChatToLatest);
  $("backToTopButton").addEventListener("click", (event) => {
    event.preventDefault();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  $("chatMessages").addEventListener("scroll", updateChatLatestButton, { passive: true });

  $("chatExpandBackdrop").addEventListener("click", closeChatExpanded);

  $("refreshProfileReport").addEventListener("click", () => generateProfileReport(true));
  $("updateProfileReport").addEventListener("click", () => generateProfileReport(true));
  $("profileReportPrev").addEventListener("click", () => setProfileReportIndex(state.profileReportIndex - 1));
  $("profileReportNext").addEventListener("click", () => setProfileReportIndex(state.profileReportIndex + 1));
  $("profileReportDots").addEventListener("click", (event) => {
    const button = event.target.closest("[data-profile-index]");
    if (button) setProfileReportIndex(Number(button.dataset.profileIndex));
  });
  $("profileReportPages").addEventListener("click", (event) => {
    if (event.target.closest("[data-profile-retry]")) generateProfileReport(true);
    if (event.target.closest("[data-profile-ask]")) askFromProfileReport();
  });
  $("profileReportViewport").addEventListener("scroll", () => {
    if (state.profileReportScrollFrame) return;
    state.profileReportScrollFrame = requestAnimationFrame(() => {
      state.profileReportScrollFrame = null;
      const viewport = $("profileReportViewport");
      if (!viewport.clientWidth || !state.profileReportPageCount) return;
      const index = clamp(Math.round(viewport.scrollLeft / viewport.clientWidth), 0, state.profileReportPageCount - 1);
      if (index !== state.profileReportIndex) {
        state.profileReportIndex = index;
        $("profileReportProgress").textContent = `${index + 1} / ${state.profileReportPageCount}`;
        $("profileReportPrev").disabled = index === 0;
        $("profileReportNext").disabled = index === state.profileReportPageCount - 1;
        $("profileReportDots").querySelectorAll("button").forEach((button, buttonIndex) => {
          const active = buttonIndex === index;
          button.classList.toggle("is-active", active);
          button.setAttribute("aria-selected", active ? "true" : "false");
        });
      }
    });
  }, { passive: true });

  document.querySelectorAll("[data-modal-close]").forEach((button) => {
    button.addEventListener("click", () => closeModal(button.dataset.modalClose));
  });

  document.querySelectorAll(".modal-backdrop").forEach((backdrop) => {
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop) closeModal(backdrop.id);
    });
  });

  $("evidenceDrawer").addEventListener("click", (event) => {
    if (event.target.closest("[data-evidence-edit]")) {
      setEvidenceEditing(true);
      return;
    }
    if (event.target.closest("[data-evidence-cancel]")) {
      setEvidenceEditing(false);
      return;
    }
    if (event.target.closest("[data-evidence-delete]")) {
      state.evidenceDeleteConfirm = true;
      renderEvidence(state.evidencePayload);
      $("evidenceContent")?.querySelector("[data-evidence-delete-cancel]")?.focus({ preventScroll: true });
      return;
    }
    if (event.target.closest("[data-evidence-delete-cancel]")) {
      state.evidenceDeleteConfirm = false;
      renderEvidence(state.evidencePayload);
      $("evidenceContent")?.querySelector("[data-evidence-delete]")?.focus({ preventScroll: true });
      return;
    }
    if (event.target.closest("[data-evidence-delete-confirm]")) {
      deleteActiveTransaction();
      return;
    }
    if (event.target === $("evidenceDrawer") || event.target.closest("[data-drawer-close]")) closeEvidence();
  });

  // 表单是 innerHTML 重绘出来的，只能在抽屉上做事件委托。
  $("evidenceDrawer").addEventListener("submit", (event) => {
    const form = event.target.closest("[data-evidence-form]");
    if (!form) return;
    event.preventDefault();
    saveEvidenceEdits(form);
  });

  $("evidenceDrawer").addEventListener("change", (event) => {
    const select = event.target.closest("select[data-inactive-current]");
    if (!select || select.value === select.dataset.inactiveCurrent) return;
    select.querySelector(`option[value="${CSS.escape(select.dataset.inactiveCurrent)}"]`)?.setAttribute("disabled", "");
  });

  $("newCategoryButton").addEventListener("click", () => {
    state.categoryDraftNew = true;
    state.categorySelectedId = null;
    state.categoryConfirm = null;
    state.categoryStatus = "";
    $("categoryModal").classList.add("is-mobile-editing");
    renderCategoryManager();
    $("categoryNameInput")?.focus();
  });

  $("categoryModal").addEventListener("click", async (event) => {
    const select = event.target.closest("[data-category-select]");
    if (select) {
      state.categoryDraftNew = false;
      state.categorySelectedId = select.dataset.categorySelect;
      state.categoryConfirm = null;
      state.categoryStatus = "";
      $("categoryModal").classList.add("is-mobile-editing");
      renderCategoryManager();
      return;
    }
    if (event.target.closest("[data-category-back]")) {
      $("categoryModal").classList.remove("is-mobile-editing");
      return;
    }
    const move = event.target.closest("[data-category-move]");
    if (move && !move.disabled) {
      const previous = state.categories.filter((item) => item.is_primary).sort((a, b) => a.primary_order - b.primary_order).map((item) => item.id);
      const index = previous.indexOf(move.dataset.categoryId);
      const target = move.dataset.categoryMove === "up" ? index - 1 : index + 1;
      if (index < 0 || target < 0 || target >= previous.length) return;
      const next = [...previous];
      [next[index], next[target]] = [next[target], next[index]];
      state.categories.forEach((item) => { if (next.includes(item.id)) item.primary_order = next.indexOf(item.id); });
      const tops = captureCategoryRowTops();
      renderCategoryList();
      playCategoryReorder(tops);
      await savePrimaryOrder(next, previous);
      // 移到头之后同方向那枚会变禁用，焦点不能就这么掉在地上，交给反方向那枚。
      const moved = (direction) =>
        document.querySelector(`[data-category-id="${CSS.escape(move.dataset.categoryId)}"][data-category-move="${direction}"]`);
      const same = moved(move.dataset.categoryMove);
      (same && !same.disabled ? same : moved(move.dataset.categoryMove === "up" ? "down" : "up"))?.focus();
      return;
    }
    if (event.target.closest("[data-category-toggle-enabled]")) {
      state.categoryConfirm = "enabled";
      renderCategoryEditor();
      return;
    }
    if (event.target.closest("[data-category-delete]")) {
      state.categoryConfirm = "delete";
      renderCategoryEditor();
      return;
    }
    if (event.target.closest("[data-category-confirm-cancel]")) {
      state.categoryConfirm = null;
      renderCategoryEditor();
      return;
    }
    const confirm = event.target.closest("[data-category-confirm-action]");
    if (confirm) {
      if (confirm.dataset.categoryConfirmAction === "delete") {
        try {
          setCategoryStatus("正在删除…", "pending");
          await categoryRequest(`./api/categories/${encodeURIComponent(state.categorySelectedId)}`, { method: "DELETE" });
          state.categorySelectedId = null;
          state.categoryConfirm = null;
          await reloadCategories();
          state.categoryStatus = "";
          renderAll();
        } catch (error) {
          setCategoryStatus(recoveryMessage(error, "删除分类"), "error");
        }
      } else {
        const item = categoryById(state.categorySelectedId);
        await patchSelectedCategory({ is_enabled: !item.is_enabled }, item.is_enabled ? "停用分类" : "恢复分类");
      }
    }
  });

  $("categoryModal").addEventListener("change", async (event) => {
    if (!event.target.matches("[data-category-primary]")) return;
    const checkbox = event.target;
    const requested = checkbox.checked;
    checkbox.disabled = true;
    const saved = await patchSelectedCategory({ is_primary: requested }, "更新常用分类");
    if (!saved && document.contains(checkbox)) {
      checkbox.checked = !requested;
      checkbox.disabled = false;
    }
  });

  $("categoryModal").addEventListener("dragstart", (event) => {
    const row = event.target.closest('[draggable="true"][data-category-row]');
    if (!row) return;
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", row.dataset.categoryRow);
    row.classList.add("is-dragging");
  });

  $("categoryModal").addEventListener("dragend", (event) => {
    event.target.closest("[data-category-row]")?.classList.remove("is-dragging");
  });

  $("categoryModal").addEventListener("dragover", (event) => {
    if (event.target.closest('[draggable="true"][data-category-row]')) event.preventDefault();
  });

  $("categoryModal").addEventListener("drop", async (event) => {
    const target = event.target.closest('[draggable="true"][data-category-row]');
    if (!target) return;
    event.preventDefault();
    const sourceId = event.dataTransfer.getData("text/plain");
    const targetId = target.dataset.categoryRow;
    if (!sourceId || sourceId === targetId) return;
    const previous = state.categories.filter((item) => item.is_primary).sort((a, b) => a.primary_order - b.primary_order).map((item) => item.id);
    const next = previous.filter((id) => id !== sourceId);
    next.splice(next.indexOf(targetId), 0, sourceId);
    state.categories.forEach((item) => { if (next.includes(item.id)) item.primary_order = next.indexOf(item.id); });
    renderCategoryList();
    await savePrimaryOrder(next, previous);
  });

  $("categoryModal").addEventListener("submit", async (event) => {
    const form = event.target.closest("[data-category-form]");
    if (!form) return;
    event.preventDefault();
    const errorNode = form.querySelector("[data-category-error]");
    const values = Object.fromEntries(new FormData(form).entries());
    values.display_name = String(values.display_name || "").trim();
    if (!values.display_name) {
      errorNode.textContent = "请填写分类名称。";
      errorNode.hidden = false;
      $("categoryNameInput")?.focus();
      return;
    }
    errorNode.hidden = true;
    if (form.dataset.mode === "create") {
      try {
        setCategoryStatus("正在创建…", "pending");
        const payload = await categoryRequest("./api/categories", { method: "POST", body: JSON.stringify(values) });
        state.categoryDraftNew = false;
        state.categorySelectedId = payload.category.id;
        await reloadCategories();
        setCategoryStatus("已创建", "success");
        renderAll();
      } catch (error) {
        errorNode.textContent = recoveryMessage(error, "创建分类");
        errorNode.hidden = false;
      }
    } else {
      await patchSelectedCategory(values);
    }
  });

  // 弹窗内、空态里出现的「打开某个弹窗」按钮
  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-open-modal]");
    if (!trigger) return;
    const target = trigger.dataset.openModal;
    const current = trigger.closest(".modal-backdrop");
    if (current && current.id !== target) closeModal(current.id);
    openModal(target);
    if (trigger.dataset.startSync === "true") syncMailData();
  });

  $("trendModeControl").addEventListener("click", (event) => {
    const button = event.target.closest("[data-trend-mode]");
    if (!button) return;
    state.trendMode = button.dataset.trendMode;
    renderTrendModal();
  });

  $("trendModeControl").addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    const buttons = Array.from($("trendModeControl").querySelectorAll("[data-trend-mode]"));
    const index = buttons.findIndex((node) => node.dataset.trendMode === state.trendMode);
    const next = buttons[(index + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length];
    event.preventDefault();
    state.trendMode = next.dataset.trendMode;
    renderTrendModal();
    $("trendModeControl").querySelector(`[data-trend-mode="${next.dataset.trendMode}"]`)?.focus();
  });

  const showTrendTooltip = (index, anchorRect) => {
    const item = state.activeTrendSeries[index];
    const tooltip = $("trendTooltip");
    if (!item) return;
    const rect = $("trendChart").getBoundingClientRect();
    tooltip.innerHTML = `
      <strong>${escapeHtml(item.title)}</strong>
      <span>${escapeHtml(formatMoney(item.amount))}</span>
      ${item.overBudget ? `<small class="trend-tooltip-warning">超出${escapeHtml(item.budgetLabel)} ${escapeHtml(formatMoney(item.overBy))}</small>` : ""}
    `;
    tooltip.hidden = false;
    tooltip.style.visibility = "hidden";

    const tooltipRect = tooltip.getBoundingClientRect();
    const gap = 12;
    const margin = 8;
    const pointerX = anchorRect.x - rect.left;
    const pointerY = anchorRect.y - rect.top;
    let left = pointerX + gap;
    let top = pointerY - tooltipRect.height - gap;

    if (left + tooltipRect.width > rect.width - margin) left = pointerX - tooltipRect.width - gap;
    if (top < margin) top = pointerY + gap;

    tooltip.style.left = `${clamp(left, margin, rect.width - tooltipRect.width - margin)}px`;
    tooltip.style.top = `${clamp(top, margin, rect.height - tooltipRect.height - margin)}px`;
    tooltip.style.visibility = "visible";
  };

  $("trendChart").addEventListener("pointermove", (event) => {
    const target = event.target.closest("[data-trend-index]");
    if (!target) {
      $("trendTooltip").hidden = true;
      return;
    }
    showTrendTooltip(Number(target.dataset.trendIndex), { x: event.clientX, y: event.clientY });
  });

  $("trendChart").addEventListener("pointerleave", () => {
    $("trendTooltip").hidden = true;
  });

  // 柱子和明细格互为入口：点哪边都选中同一期，点图表空白处取消。
  $("trendChart").addEventListener("click", (event) => {
    const slot = event.target.closest(".trend-slot");
    setTrendSelection(slot ? Number(slot.dataset.trendIndex) : null);
  });

  // <g role="button"> 不像原生按钮那样把回车翻译成 click，得自己接。
  $("trendChart").addEventListener("keydown", (event) => {
    if (!["Enter", " "].includes(event.key)) return;
    const slot = event.target.closest(".trend-slot");
    if (!slot) return;
    event.preventDefault();
    setTrendSelection(Number(slot.dataset.trendIndex));
  });

  $("trendBreakdown").addEventListener("click", (event) => {
    // 箭头优先：它和格子是并列按钮，点箭头不该只是高亮一下
    const jump = event.target.closest("[data-trend-jump]");
    if (jump) {
      jumpToTrendPeriod(Number(jump.dataset.trendJump));
      return;
    }
    const body = event.target.closest(".trend-cell-body");
    if (!body) return;
    setTrendSelection(Number(body.dataset.trendIndex));
  });

  // 回到当前那一期的高亮，不是取消选中。
  $("trendBudgetReset").addEventListener("click", () => setTrendSelection(currentTrendIndex()));

  // 键盘用户也能读到每根柱子的数值
  $("trendChart").addEventListener(
    "focusin",
    (event) => {
      const slot = event.target.closest(".trend-slot");
      if (!slot) return;
      const box = slot.querySelector(".trend-col").getBoundingClientRect();
      showTrendTooltip(Number(slot.dataset.trendIndex), { x: box.left + box.width / 2, y: box.top });
    },
    true,
  );

  $("trendChart").addEventListener(
    "focusout",
    () => {
      $("trendTooltip").hidden = true;
    },
    true,
  );

  $("budgetForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const inputs = [
      { id: "dayBudgetInput", name: "日预算" },
      { id: "weekBudgetInput", name: "周预算" },
      { id: "monthBudgetInput", name: "月预算" },
    ];
    clearBudgetError();

    const invalid = inputs.find(({ id }) => {
      const raw = $(id).value.trim();
      return raw !== "" && !(Number(raw) >= 0);
    });
    if (invalid) {
      const error = $("budgetError");
      error.textContent = `${invalid.name}需要是 0 或更大的数字。`;
      error.hidden = false;
      $(invalid.id).closest(".field-control").classList.add("has-error");
      $(invalid.id).focus();
      return;
    }

    saveBudgets({
      day: Math.max(0, Number($("dayBudgetInput").value || 0)),
      week: Math.max(0, Number($("weekBudgetInput").value || 0)),
      month: Math.max(0, Number($("monthBudgetInput").value || 0)),
    });
    closeModal("budgetModal");
    showToast("预算已更新");
  });

  $("budgetForm").addEventListener("input", clearBudgetError);

  $("resetBudgetButton").addEventListener("click", () => {
    saveBudgets({ ...defaultBudgets });
    renderBudgetForm();
  });

  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      const overlay = document.querySelector(".opening-overlay");
      if (overlay && document.body.classList.contains("motion-running")) {
        window.skipCfoOpening?.();
        return;
      }
      if (state.chatExpanded) {
        closeChatExpanded();
        return;
      }
      const modal = topmostOpenModal();
      if (!modal) {
        if (!$("evidenceDrawer").hidden) closeEvidence();
      } else {
        closeModal(modal.id);
      }
      return;
    }

    const profileOpen = !$("profileReportModal").hidden;
    const tag = document.activeElement?.tagName;
    if (profileOpen && tag !== "INPUT" && tag !== "TEXTAREA" && ["ArrowLeft", "ArrowRight"].includes(event.key)) {
      event.preventDefault();
      setProfileReportIndex(state.profileReportIndex + (event.key === "ArrowRight" ? 1 : -1));
      return;
    }

    trapFocus(event);

    // "/" 聚焦提问框；输入态里不劫持
    if (event.key === "/" && tag !== "INPUT" && tag !== "TEXTAREA") {
      event.preventDefault();
      $("chatInput").focus();
    }
  });

  document.querySelector(".period-control").addEventListener("click", (event) => {
    const button = event.target.closest(".period-btn");
    if (button) selectPeriod(button);
  });

  document.querySelector(".period-control").addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    const buttons = periodButtons();
    const index = buttons.indexOf(document.activeElement);
    if (index < 0) return;
    event.preventDefault();
    const next =
      event.key === "Home"
        ? buttons[0]
        : event.key === "End"
          ? buttons[buttons.length - 1]
          : buttons[(index + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length];
    // 方向键路过「自定义」时只移焦点：光是走过去就弹出面板太粗暴，
    // 真要用它，回车/空格自然会触发 click。
    if (next.dataset.period === "custom") {
      next.focus();
      return;
    }
    selectPeriod(next, { focus: true });
  });

  $("periodClear").addEventListener("click", () => clearCustomRange({ focus: true }));

  $("rangePresets").addEventListener("click", (event) => {
    const button = event.target.closest("[data-range-preset]");
    if (!button) return;
    // 再点一次选中的那枚就是取消选中：之前点了没反应，看着像卡住了。
    if (button.getAttribute("aria-pressed") === "true") {
      state.rangeDraft = null;
      state.rangeHoverKey = null;
      renderRangePicker();
      return;
    }
    const range = presetRange(button.dataset.rangePreset);
    if (!range) return;
    state.rangeDraft = { start: range.start, end: range.end };
    state.rangeHoverKey = null;
    state.rangeFocusKey = dateKey(range.start);
    state.rangeCursor = rangeAnchorMonth(range);
    renderRangePicker();
  });

  $("rangePrevMonth").addEventListener("click", () => shiftRangeCursor(-1));
  $("rangeNextMonth").addEventListener("click", () => shiftRangeCursor(1));

  const rangeMonths = $("rangeMonths");
  rangeMonths.addEventListener("click", (event) => {
    const cell = event.target.closest("[data-range-day]");
    if (cell && !cell.disabled) pickRangeDay(cell.dataset.rangeDay);
  });

  /*
   * 只点了起点时，划过哪天就预览到哪天——但这套只接给真有指针的设备。
   * 触摸屏上 iOS 会在点按时先发 mouseover：第二下的 click 一旦被吞掉，
   * 草稿里其实还没有终点，小结却已经被这条预览撑成了一整段；等手指移向「应用」，
   * 网格的 mouseleave 把预览清掉，按下去落地的就只剩起点那一天。
   */
  if (window.matchMedia?.("(hover: hover)").matches) {
    rangeMonths.addEventListener("mouseover", (event) => {
      if (state.rangeDraft?.end) return;
      const cell = event.target.closest("[data-range-day]");
      if (!cell || cell.disabled || state.rangeHoverKey === cell.dataset.rangeDay) return;
      state.rangeHoverKey = cell.dataset.rangeDay;
      paintRangeSelection();
      renderRangeSummary();
    });

    rangeMonths.addEventListener("mouseleave", () => {
      if (!state.rangeHoverKey) return;
      state.rangeHoverKey = null;
      paintRangeSelection();
      renderRangeSummary();
    });
  }

  rangeMonths.addEventListener("keydown", handleRangeGridKeydown);

  $("rangeCancel").addEventListener("click", () => closeModal("rangeModal"));

  $("rangeApply").addEventListener("click", () => {
    const draft = normalizedDraft();
    closeModal("rangeModal");
    if (draft) applyCustomRange(draft);
  });

  window.addEventListener("resize", () => {
    movePeriodThumb();
    // 轨道是否溢出只有量过才知道，宽度一变就要重量一次。
    syncTrackOverflow();
    // 单月 ↔ 双月是断点切换的，面板开着时要跟着重画。
    if (!$("rangeModal").hidden) renderRangePicker();
  });

  $("decisionFeed").addEventListener("click", (event) => {
    const button = event.target.closest("[data-decision-action]");
    if (!button) return;
    const { decisionAction, category, merchant, uid, mode, question } = button.dataset;
    if (decisionAction === "ask") {
      askFromInsight(question);
      return;
    }
    if (decisionAction === "evidence") {
      openEvidence(uid);
      return;
    }
    if (decisionAction === "trend") {
      if (mode) state.trendMode = mode;
      openModal("trendModal");
      return;
    }
    if (decisionAction === "ledger") focusLedger({ category, merchant });
  });

  $("filterBar").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    if (button.hasAttribute("data-category-manage")) {
      state.ledgerFilterExpanded = false;
      renderFilters();
      document.querySelector("[data-category-manage]")?.focus({ preventScroll: true });
      openModal("categoryModal");
      return;
    }
    if (button.dataset.filterAction === "toggle-more") {
      state.ledgerFilterExpanded = !state.ledgerFilterExpanded;
      renderFilters();
      document.querySelector('[data-filter-action="toggle-more"]')?.focus({ preventScroll: true });
      window.refreshCfoMotion?.({ scope: "ledger", quiet: true });
      return;
    }
    if (button.hasAttribute("data-clear-merchant")) {
      state.merchantFocus = "";
      state.ledgerPage = 1;
      renderFilters();
      renderTransactions();
      window.refreshCfoMotion?.({ scope: "ledger" });
      return;
    }
    if (!button.dataset.filter) return;
    // 手动选分类＝重新划定范围，之前带过来的商户约束到此为止。
    state.merchantFocus = "";
    state.filter = button.dataset.filter;
    state.ledgerFilterExpanded = false;
    state.ledgerPage = 1;
    renderFilters();
    renderTransactions();
    window.refreshCfoMotion?.({ scope: "ledger" });
  });

  // 空态里的「查看全部分类」也走同一条路径
  $("transactionList").addEventListener("click", (event) => {
    const button = event.target.closest("[data-filter]");
    if (button) {
      state.filter = button.dataset.filter;
      state.merchantFocus = "";
      state.ledgerPage = 1;
      renderFilters();
      renderTransactions();
      return;
    }
    const transaction = event.target.closest("[data-transaction-uid]");
    if (transaction) openEvidence(transaction.dataset.transactionUid);
  });

  $("transactionList").addEventListener("keydown", (event) => {
    if (!['Enter', ' '].includes(event.key)) return;
    const transaction = event.target.closest("[data-transaction-uid]");
    if (!transaction) return;
    event.preventDefault();
    openEvidence(transaction.dataset.transactionUid);
  });

  $("correctionQueue").addEventListener("click", (event) => {
    const transaction = event.target.closest("[data-transaction-uid]");
    if (transaction) openEvidence(transaction.dataset.transactionUid);
  });

  $("syncItemList").addEventListener("click", (event) => {
    const transaction = event.target.closest("[data-transaction-uid]");
    if (transaction?.dataset.transactionUid) openEvidence(transaction.dataset.transactionUid);
  });

  // 捕获阶段：#filterBar 自己的处理器会重建 innerHTML，冒泡时 target 已脱离文档，
  // closest("#filterBar") 就永远是 null 了。
  document.addEventListener(
    "click",
    (event) => {
      if (!state.ledgerFilterExpanded) return;
      if (event.target.closest?.("#filterBar")) return;
      state.ledgerFilterExpanded = false;
      renderFilters();
    },
    true,
  );

  $("ledgerPagination").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button || button.disabled || !button.dataset.pageAction) return;
    if (button.dataset.pageAction === "prev") state.ledgerPage -= 1;
    if (button.dataset.pageAction === "next") state.ledgerPage += 1;
    renderTransactions();
    document.querySelector(".table-wrap")?.scrollIntoView({ block: "nearest" });
    window.refreshCfoMotion?.({ scope: "ledger" });
  });

  $("ledgerPagination").addEventListener("submit", (event) => {
    const form = event.target.closest("[data-page-jump-form]");
    if (!form) return;
    event.preventDefault();
    const input = form.querySelector("input");
    const requestedPage = Number.parseInt(input?.value || "", 10);
    const maxPage = Number.parseInt(input?.max || "1", 10);
    if (!Number.isFinite(requestedPage)) return;
    state.ledgerPage = Math.min(Math.max(requestedPage, 1), maxPage);
    renderTransactions();
    window.refreshCfoMotion?.({ scope: "ledger" });
  });

  updateQuickPrompts();
  $("rerollPrompts").addEventListener("click", () => {
    rollPrompts({ exclude: state.promptPicks });
    state.promptRailPulse = true;
    renderPromptRail();
    window.refreshCfoMotion?.({ scope: "global", quiet: true });
  });

  // 委托在 .chat-foot 上：三档轨道都在里面，一个处理器全覆盖。
  document.querySelector(".chat-foot").addEventListener("click", (event) => {
    const tab = event.target.closest("[data-prompt-tab]");
    if (tab) {
      selectPromptTab(tab.dataset.promptTab);
      return;
    }
    const button = event.target.closest("button[data-question]");
    if (!button || button.disabled) return;
    submitQuestion(button.dataset.question, { scoped: button.dataset.questionScope !== "free" });
  });

  // tablist 的标准键盘行为：左右在三档间走，Home/End 跳到两端。
  document.querySelector(".prompt-tabs").addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    const tabs = Array.from(document.querySelectorAll("[data-prompt-tab]"))
      .filter((node) => !node.hidden && node.dataset.squeeze !== "out");
    if (tabs.length < 2) return;
    event.preventDefault();
    const current = tabs.findIndex((node) => node.dataset.promptTab === state.promptTabActive);
    const step = event.key === "ArrowLeft" ? -1 : 1;
    const next = event.key === "Home"
      ? 0
      : event.key === "End"
        ? tabs.length - 1
        : (current + step + tabs.length) % tabs.length;
    selectPromptTab(tabs[next].dataset.promptTab, { focus: true });
  });

  const promptManager = $("promptManager");
  promptManager.addEventListener("click", (event) => {
    const move = event.target.closest("[data-prompt-move]");
    if (move) {
      moveCustomPrompt(move.dataset.promptId, move.dataset.promptMove);
      return;
    }
    const edit = event.target.closest("[data-prompt-edit]");
    if (edit) {
      state.promptEditing = edit.dataset.promptEdit;
      state.promptConfirm = null;
      setPromptStatus("");
      renderPromptManager();
      $("promptManager").querySelector("input[name='label']")?.focus({ preventScroll: true });
      return;
    }
    if (event.target.closest("[data-prompt-cancel-edit]")) {
      state.promptEditing = null;
      setPromptStatus("");
      renderPromptManager();
      return;
    }
    const confirmDelete = event.target.closest("[data-prompt-confirm-delete]");
    if (confirmDelete) {
      state.promptConfirm = confirmDelete.dataset.promptConfirmDelete;
      renderPromptManager();
      return;
    }
    if (event.target.closest("[data-prompt-cancel-delete]")) {
      state.promptConfirm = null;
      renderPromptManager();
      return;
    }
    const remove = event.target.closest("[data-prompt-delete]");
    if (remove) deleteCustomPrompt(remove.dataset.promptDelete);
  });

  // 表单每次都是重新 innerHTML 出来的，所以只能委托：预览跟着输入实时更新。
  promptManager.addEventListener("input", (event) => {
    const form = event.target.closest("[data-prompt-form]");
    if (form) syncPromptPreview(form);
  });
  promptManager.addEventListener("change", (event) => {
    const form = event.target.closest("[data-prompt-form]");
    if (form) syncPromptPreview(form);
  });
  promptManager.addEventListener("submit", (event) => {
    const form = event.target.closest("[data-prompt-form]");
    if (!form) return;
    event.preventDefault();
    submitPromptForm(form);
  });

  $("chatForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = $("chatInput");
    const question = input.value.trim();
    if (!question) {
      input.focus();
      return;
    }
    input.value = "";
    submitQuestion(question);
  });

  document.querySelectorAll(".nav-item").forEach((item) => {
    item.addEventListener("click", () => {
      if (item.dataset.navSection) setActiveNav(item.dataset.navSection);
    });
  });

  wireScrollSpy();
  movePeriodThumb();
  if (document.fonts?.ready) document.fonts.ready.then(movePeriodThumb);
}

/* ------------------------------- 启动 ------------------------------- */

async function loadSnapshot() {
  const response = await fetch("./data.json", { cache: "no-store" });
  if (!response.ok) throw new Error(`data.json 加载失败：HTTP ${response.status}`);
  const data = await response.json();
  state.generatedAt = data.generated_at || null;
  state.demo = Boolean(data.demo);
  state.classificationPendingCount = Number(data.classification_pending_count || 0);
  state.transactions = (data.transactions || []).sort((a, b) => {
    const aTime = parseDate(a.paid_at || a.captured_at || a.created_at).getTime() || 0;
    const bTime = parseDate(b.paid_at || b.captured_at || b.created_at).getTime() || 0;
    return bTime - aTime;
  });
  state.hasLoaded = true;
}

/** 致命错误不再清空 body：保留外壳，只在主区域给一块可重试的说明。 */
function renderFatalError(title, message, { retry = true } = {}) {
  const host = document.querySelector(".main") || document.body;
  document.body.classList.remove("app-loading", "motion-running");
  document.body.classList.add("motion-ready", "motion-complete");
  host.innerHTML = `
    <section class="app-error" role="alert">
      <h1>${escapeHtml(title)}</h1>
      <p>${escapeHtml(message)}</p>
      ${retry ? `<button class="btn btn-primary" type="button" data-retry-boot>重新加载</button>` : ""}
    </section>
  `;
  host.querySelector("[data-retry-boot]")?.addEventListener("click", () => window.location.reload());
}

async function boot() {
  if (window.location.protocol === "file:") {
    renderFatalError(
      "请通过本地服务打开",
      "当前是 file:// 页面，浏览器会阻止读取 data.json。请打开 http://localhost:8091/ 后重试。",
      { retry: false },
    );
    return;
  }

  const dataReady = Promise.all([
    loadSnapshot(),
    reloadCategories({ preserveSelection: false }),
    loadCustomPrompts(),
  ]).then(() => {
    rollPrompts();
    renderAll();
    if (!$("trendModal").hidden) renderTrendModal();
    fetchProfileReportMetadata().catch(() => {});
  });
  window.cfoDataReady = dataReady;

  addMessage("agent", "账本已经同步好了，你可以来咨询任何一笔消费，尽管来问吧🤗");
  wireInteractions();
  window.initCfoMotion?.();
  await dataReady;
}

boot().catch((error) => {
  window.skipCfoOpening?.();
  renderFatalError("账本加载失败", error.message);
});
