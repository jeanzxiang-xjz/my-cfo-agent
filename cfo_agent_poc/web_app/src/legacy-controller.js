const currency = new Intl.NumberFormat("zh-CN", {
  style: "currency",
  currency: "CNY",
  maximumFractionDigits: 2,
});

const categoryNames = {
  coffee_tea: "咖啡/奶茶",
  food_delivery: "外卖/餐饮",
  parking: "停车交通",
  car_charging: "车辆充电",
  auto: "爱车养车",
  groceries: "超市便利",
  fruit: "水果鲜果",
  bakery: "烘焙面包",
  education: "教育考试",
  books: "图书书店",
  ecommerce: "网购",
  transport: "交通",
  healthcare: "医疗",
  investment: "投资理财",
  property: "物业生活",
  telecom: "通信充值",
  entertainment: "演出票务",
  credit_repayment: "信用借还",
  utilities: "水电燃缴费",
  stationery: "文具用品",
  uncategorized: "未分类",
};

const paymentAppNames = {
  wechat: "微信",
  alipay: "支付宝",
};

const ledgerPageSize = 10;
const primaryLedgerCategories = ["all", "books", "food_delivery", "groceries", "property", "car_charging"];
const budgetStorageKey = "ericCfoBudgets";
const defaultBudgets = {
  day: 300,
  week: 2000,
  month: 12000,
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
  generatedAt: null,
  period: "today",
  filter: "all",
  ledgerFilterExpanded: false,
  ledgerPage: 1,
  chatHistory: [],
  chatBusy: false,
  syncBusy: false,
  budgets: loadBudgetConfig(),
  trendMode: "day",
  activeTrendSeries: [],
};

function $(id) {
  return document.getElementById(id);
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

function animateSplitText(node) {
  if (!node || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;

  const skipTags = new Set(["A", "CODE", "PRE", "SCRIPT", "STYLE", "TABLE", "TBODY", "TD", "TFOOT", "TH", "THEAD", "TR"]);
  const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT, {
    acceptNode(textNode) {
      if (!textNode.nodeValue?.trim()) return NodeFilter.FILTER_REJECT;
      let parent = textNode.parentElement;
      while (parent && parent !== node) {
        if (skipTags.has(parent.tagName)) return NodeFilter.FILTER_REJECT;
        parent = parent.parentElement;
      }
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  const textNodes = [];
  while (walker.nextNode()) textNodes.push(walker.currentNode);

  let index = 0;
  textNodes.forEach((textNode) => {
    const fragment = document.createDocumentFragment();
    Array.from(textNode.nodeValue).forEach((char) => {
      if (/\s/.test(char)) {
        fragment.appendChild(document.createTextNode(char));
        return;
      }
      const span = document.createElement("span");
      span.className = "split-answer-char";
      span.style.setProperty("--split-index", String(Math.min(index, 90)));
      span.textContent = char;
      fragment.appendChild(span);
      index += 1;
    });
    textNode.replaceWith(fragment);
  });

  if (index > 0) node.classList.add("split-answer-active");
}

function setMessageContent(node, role, text, options = {}) {
  if (role === "agent") {
    node.classList.add("markdown-message");
    node.classList.remove("split-answer-active");
    node.innerHTML = renderMarkdown(text);
    if (options.split) animateSplitText(node);
    return;
  }
  node.classList.remove("split-answer-active");
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
  const dates = state.transactions
    .map((tx) => parseDate(tx.paid_at))
    .filter((date) => !Number.isNaN(date.getTime()))
    .sort((a, b) => b - a);

  if (dates.length) return dates[0];
  if (state.generatedAt) return parseDate(state.generatedAt);
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

function sum(transactions) {
  return transactions.reduce((total, tx) => total + normalizeAmount(tx), 0);
}

function clamp(value, min, max) {
  const safeMax = Math.max(min, max);
  return Math.min(Math.max(value, min), safeMax);
}

function scopedTransactions(period = state.period) {
  const anchor = getAnchorDate();
  return state.transactions.filter((tx) => {
    const paidAt = parseDate(tx.paid_at);
    if (Number.isNaN(paidAt.getTime())) return false;
    if (period === "today") return sameDay(paidAt, anchor);
    if (period === "week") return inSameWeek(paidAt, anchor);
    if (period === "month") return inSameMonth(paidAt, anchor);
    return true;
  });
}

function transactionsBetween(start, end) {
  return state.transactions.filter((tx) => {
    const paidAt = parseDate(tx.paid_at);
    return !Number.isNaN(paidAt.getTime()) && paidAt >= start && paidAt < end;
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

function averageConfidence(transactions) {
  if (!transactions.length) return 0;
  return Math.round((transactions.reduce((total, tx) => total + Number(tx.confidence || 0), 0) / transactions.length) * 100);
}

function formatMoney(value) {
  return currency.format(Number(value || 0));
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

function periodName(period = state.period) {
  if (period === "today") return "今日净支出";
  if (period === "week") return "本周累计支出";
  if (period === "month") return "本月累计支出";
  return "全部记录支出";
}

function periodLabel(period = state.period) {
  if (period === "today") return "今日";
  if (period === "week") return "本周";
  if (period === "month") return "本月";
  return "全部";
}

function categoryLabel(category) {
  return categoryNames[category] || category || "未分类";
}

function filterButton(category, options = {}) {
  const label = category === "all" ? "全部" : categoryLabel(category);
  const classes = ["ledger-filter-chip"];
  if (state.filter === category) classes.push("active");
  if (options.current) classes.push("current-extra");
  return `<button class="${classes.join(" ")}" data-filter="${escapeHtml(category)}" type="button">${escapeHtml(label)}</button>`;
}

function paymentLabel(app) {
  return paymentAppNames[app] || app || "未知渠道";
}

function categorySummary(transactions) {
  const top = topCategory(transactions);
  if (!top) return "暂无场景";
  return `${categoryLabel(top[0])} ${formatMoney(top[1].amount)}`;
}

function budgetLabel(mode = state.trendMode) {
  if (mode === "day") return "日预算";
  if (mode === "week") return "周预算";
  return "月预算";
}

function trendModeTitle(mode = state.trendMode) {
  if (mode === "day") return "近7天每日支出";
  if (mode === "week") return "本月周度支出";
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
      };
    });
  }

  if (mode === "week") {
    const monthStart = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
    const monthEnd = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0);
    const series = [];
    let cursor = monthStart;

    while (cursor <= anchor && cursor <= monthEnd) {
      const endDate = new Date(Math.min(weekEndFor(cursor), monthEnd));
      const end = addDays(startOfDay(endDate), 1);
      series.push({
        label: `第${series.length + 1}周`,
        title: `${formatShortDate(cursor)}-${formatShortDate(endDate)}`,
        amount: sumBetween(cursor, end),
      });
      cursor = end;
    }
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
    });
  }
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

function trendSubtitle(mode = state.trendMode) {
  if (mode === "day") return "现金流趋势展示近 7 天每日支出。";
  if (mode === "week") return "现金流趋势展示本月第一周到当前周。";
  return "现金流趋势展示本年第一月到当前月。";
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

function trendChartSvg(series, mode) {
  const width = 760;
  const height = 318;
  const padding = { top: 28, right: 22, bottom: 48, left: 58 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;
  const budget = state.budgets[mode] || 0;
  const maxAmount = Math.max(...series.map((item) => item.amount), budget, 1);
  const topValue = maxAmount * 1.22;
  const xFor = (index) => {
    if (series.length <= 1) return padding.left + chartWidth / 2;
    return padding.left + (chartWidth * index) / (series.length - 1);
  };
  const yFor = (value) => padding.top + chartHeight - (Math.max(value, 0) / topValue) * chartHeight;
  const points = series.map((item, index) => ({
    ...item,
    x: xFor(index),
    y: yFor(item.amount),
  }));
  const linePath = points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L ${points[points.length - 1]?.x || padding.left} ${height - padding.bottom} L ${points[0]?.x || padding.left} ${height - padding.bottom} Z`;
  const budgetY = yFor(budget);
  const budgetLabelY = Math.min(Math.max(budgetY - 8, padding.top + 14), height - padding.bottom - 8);
  const grid = Array.from({ length: 5 }, (_, index) => {
    const value = (topValue / 4) * index;
    const y = yFor(value);
    return `
      <line class="trend-grid-line" x1="${padding.left}" x2="${width - padding.right}" y1="${y}" y2="${y}"></line>
      <text class="trend-axis-value" x="${padding.left - 12}" y="${y + 4}" text-anchor="end">${Math.round(value)}</text>
    `;
  }).reverse().join("");

  return `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(trendModeTitle(mode))}">
      <defs>
        <linearGradient id="trendAreaGradient" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stop-color="rgba(82, 241, 207, 0.28)" />
          <stop offset="100%" stop-color="rgba(82, 241, 207, 0.02)" />
        </linearGradient>
      </defs>
      ${grid}
      <line class="trend-budget-line" x1="${padding.left}" x2="${width - padding.right}" y1="${budgetY}" y2="${budgetY}"></line>
      <text class="trend-budget-text" x="${padding.left + 10}" y="${budgetLabelY}" text-anchor="start">${escapeHtml(budgetLabel(mode))}</text>
      <path class="trend-area" d="${areaPath}"></path>
      <path class="trend-line" d="${linePath}"></path>
      ${points.map((point, index) => {
        const barHeight = height - padding.bottom - point.y;
        const alertX = point.x;
        const alertY = Math.max(padding.top + 10, point.y - 18);
        return `
          <rect class="trend-bar ${point.overBudget ? "over-budget" : ""}" x="${point.x - 9}" y="${point.y}" width="18" height="${Math.max(barHeight, 2)}" rx="9"></rect>
          <circle class="trend-point ${point.overBudget ? "over-budget" : ""}" data-trend-index="${index}" cx="${point.x}" cy="${point.y}" r="6"></circle>
          ${point.overBudget ? `
            <g class="trend-alert" data-trend-index="${index}" aria-label="超出${escapeHtml(point.budgetLabel)}">
              <circle class="trend-alert-badge" cx="${alertX}" cy="${alertY}" r="10"></circle>
              <text class="trend-alert-mark" x="${alertX}" y="${alertY + 4}" text-anchor="middle">!</text>
            </g>
          ` : ""}
          <rect class="trend-hit-zone" data-trend-index="${index}" x="${point.x - 28}" y="${padding.top}" width="56" height="${chartHeight}"></rect>
          <text class="trend-axis-label" x="${point.x}" y="${height - 18}" text-anchor="middle">${escapeHtml(point.label)}</text>
        `;
      }).join("")}
    </svg>
  `;
}

function renderTrendModal() {
  const mode = state.trendMode;
  const series = annotateTrendSeries(trendSeries(mode), mode);
  state.activeTrendSeries = series;
  const spend = currentBudgetSpend(mode);
  const budget = state.budgets[mode] || 0;
  const usage = budget > 0 ? Math.round((spend / budget) * 100) : 0;
  const remaining = budget - spend;
  const average = remaining / remainingBudgetDays(mode);

  $("trendSubtitle").textContent = trendSubtitle(mode);
  $("trendChart").innerHTML = trendChartSvg(series, mode);
  $("trendBudgetLabel").textContent = budgetLabel(mode);
  $("trendBudgetValue").textContent = formatMoney(budget);
  $("trendBudgetPercent").textContent = `${usage}%`;
  $("trendBudgetRemaining").textContent = formatMoney(remaining);
  $("trendBudgetAverageLabel").textContent = mode === "day" ? "计算口径" : "日均可用";
  $("trendBudgetAverage").textContent = mode === "day" ? "按今日消费计算" : formatMoney(average);
  $("trendBudgetProgress").style.width = `${Math.min(Math.max(usage, 0), 100)}%`;

  document.querySelectorAll("[data-trend-mode]").forEach((button) => {
    button.classList.toggle("active", button.dataset.trendMode === mode);
  });
}

function renderBudgetForm() {
  $("dayBudgetInput").value = state.budgets.day;
  $("weekBudgetInput").value = state.budgets.week;
  $("monthBudgetInput").value = state.budgets.month;
}

function saveBudgets(budgets) {
  state.budgets = budgets;
  localStorage.setItem(budgetStorageKey, JSON.stringify(budgets));
  if (!$("trendModal").hidden) renderTrendModal();
}

function openModal(id) {
  const modal = $(id);
  if (!modal || modal.classList.contains("modal-visible")) return;
  modal.hidden = false;
  document.body.classList.add("modal-open");
  if (id === "trendModal") renderTrendModal();
  if (id === "budgetModal") renderBudgetForm();
  if (id === "syncModal") resetSyncModal();
  requestAnimationFrame(() => {
    modal.classList.add("modal-visible");
  });
}

function closeModal(id) {
  const modal = $(id);
  if (!modal || modal.hidden) return;
  modal.classList.remove("modal-visible");
  window.setTimeout(() => {
    if (modal.classList.contains("modal-visible")) return;
    modal.hidden = true;
    if ($("trendModal").hidden && $("budgetModal").hidden && $("syncModal").hidden) {
      document.body.classList.remove("modal-open");
    }
  }, 430);
  $("trendTooltip").hidden = true;
}

function renderHeader() {
  const month = scopedTransactions("month");
  const latest = state.transactions[0];
  const categories = Object.keys(groupByCategory(month));

  $("headerSummary").textContent = latest
    ? `已解析 ${state.transactions.length} 笔消费。最近一笔消费是 ${displayDate(latest.paid_at)} 的 ${latest.merchant || latest.thing || "消费"}，本月覆盖 ${categories.length} 个消费场景。`
    : "暂无可展示账单。";
}

function renderMetrics() {
  const selected = scopedTransactions(state.period);
  const selectedSpend = sum(selected);
  const maxTx = largest(selected);
  const top = topCategory(selected);
  const selectedCategories = Object.keys(groupByCategory(selected));

  $("periodLabel").textContent = periodName();
  $("coreAmount").textContent = formatMoney(selectedSpend);
  $("primaryMeta").textContent = `${selected.length} 笔消费 | ${selectedCategories.length} 个消费场景 | ${categorySummary(selected)}`;
  $("coreNarrative").textContent = top
    ? `${periodLabel()}权重最高的是 ${categoryLabel(top[0])}，Agent 正在把该周期的金额、频率、支付渠道和单笔峰值一起分析。`
    : "等待 Agent 建立当前消费画像。";
  $("monthSpend").textContent = formatMoney(selectedSpend);
  $("budgetUsage").textContent = `${selected.length} 笔`;
  $("largestSpend").textContent = maxTx ? formatMoney(maxTx.amount) : "--";
  $("confidenceScore").textContent = `${averageConfidence(selected)}%`;
  $("signalMeta").textContent = `${periodLabel()}样本 ${selected.length} 笔 | ${averageConfidence(selected)}% 置信`;
  $("analysisState").textContent = selected.length ? "Active" : "Learning";
}

function renderCoreNodes() {
  const selected = scopedTransactions(state.period);
  const grouped = groupByCategory(selected);
  const total = Math.max(sum(selected), 1);
  const entries = Object.entries(grouped).sort((a, b) => b[1].amount - a[1].amount).slice(0, 4);

  $("coreNodes").innerHTML = entries.length
    ? entries
        .map(([category, value]) => {
          const share = Math.round((value.amount / total) * 100);
          return `
            <div class="node-chip">
              ${escapeHtml(categoryLabel(category))}
              <strong>${share}%</strong>
            </div>
          `;
        })
        .join("")
    : `<div class="node-chip">等待消费节点<strong>0%</strong></div>`;
}

function buildDecisionItems() {
  const selected = scopedTransactions(state.period);
  const selectedSpend = sum(selected);
  const maxTx = largest(selected);
  const grouped = groupByCategory(selected);
  const top = topCategory(selected);
  const foodAmount = (grouped.food_delivery?.amount || 0) + (grouped.coffee_tea?.amount || 0);
  const foodCount = (grouped.food_delivery?.count || 0) + (grouped.coffee_tea?.count || 0);
  const apps = [...new Set(selected.map((tx) => paymentLabel(tx.payment_app)).filter(Boolean))];
  const topShare = top ? Math.round((top[1].amount / Math.max(selectedSpend, 1)) * 100) : 0;
  const label = periodLabel();

  return [
    {
      type: "FACT",
      tone: "normal",
      title: `${label}共 ${selected.length} 笔消费`,
      copy: `当前选择周期的总支出为 ${formatMoney(selectedSpend)}，覆盖 ${Object.keys(grouped).length} 个消费场景。`,
    },
    {
      type: "PATTERN",
      tone: "normal",
      title: top ? `${categoryLabel(top[0])} 是${label}最高权重` : "样本仍在建立",
      copy: top ? `该场景占当前选择周期支出的 ${topShare}%，说明现金流变化主要由少数场景驱动。` : "继续积累账单后，Agent 会开始判断稳定习惯。",
    },
    {
      type: "RISK",
      tone: foodCount >= 2 ? "warn" : "normal",
      title: foodCount >= 2 ? `餐饮茶饮出现 ${foodCount} 次` : "餐饮频率暂无压力",
      copy: foodCount >= 2 ? `餐饮和茶饮合计 ${formatMoney(foodAmount)}。建议先观察频率，再决定是否设置预算线。` : "当前餐饮样本偏少，先保持监控。",
    },
    {
      type: "ACTION",
      tone: "normal",
      title: maxTx ? `最大单笔来自 ${maxTx.merchant || maxTx.product || "未知商户"}` : "暂无最大单笔",
      copy: maxTx ? `${formatMoney(maxTx.amount)} 已被标记为关键节点。支付渠道覆盖 ${apps.join("、") || "暂无"}。` : "新账单进入后会自动标记关键节点。",
    },
  ];
}

function renderDecisionFeed() {
  $("decisionFeed").innerHTML = buildDecisionItems()
    .map((item) => `
      <div class="decision-item ${item.tone === "warn" ? "warn" : ""}">
        <div class="decision-type">${escapeHtml(item.type)}</div>
        <div class="decision-copy">
          <strong>${escapeHtml(item.title)}</strong>
          <span>${escapeHtml(item.copy)}</span>
        </div>
      </div>
    `)
    .join("");
}

function renderCategoryStack() {
  const selected = scopedTransactions(state.period);
  const grouped = groupByCategory(selected);
  const entries = Object.entries(grouped).sort((a, b) => b[1].amount - a[1].amount);
  const total = Math.max(sum(selected), 1);

  $("categoryCount").textContent = `${entries.length} 类`;
  $("categoryStack").innerHTML = entries.length
    ? entries
        .map(([category, value]) => {
          const share = Math.round((value.amount / total) * 100);
          return `
            <div class="category-row">
              <div class="category-name">
                <strong>${escapeHtml(categoryLabel(category))}</strong>
                <span>${value.count} 笔 | ${share}% 权重</span>
              </div>
              <div class="category-value">${escapeHtml(formatMoney(value.amount))}</div>
            </div>
          `;
        })
        .join("")
    : `<div class="empty-state">暂无分类数据。</div>`;
}

function renderFilters() {
  const categories = ["all", ...new Set(state.transactions.map((tx) => tx.category || "uncategorized"))];
  const categorySet = new Set(categories);
  const primaryCategories = primaryLedgerCategories.filter((category) => categorySet.has(category));
  const otherCategories = categories.filter((category) => !primaryCategories.includes(category));
  const selectedIsExtra = state.filter !== "all" && otherCategories.includes(state.filter);
  const panelClasses = `filter-popover${state.ledgerFilterExpanded ? " open" : ""}`;

  $("filterBar").classList.toggle("expanded", state.ledgerFilterExpanded);
  $("filterBar").innerHTML = `
    <div class="filter-strip">
      <div class="filter-strip-scroll">
        ${primaryCategories.map((category) => filterButton(category)).join("")}
        ${selectedIsExtra ? filterButton(state.filter, { current: true }) : ""}
      </div>
      ${otherCategories.length ? `
        <button class="ledger-filter-more${state.ledgerFilterExpanded ? " active" : ""}" data-filter-action="toggle-more" type="button" aria-expanded="${state.ledgerFilterExpanded ? "true" : "false"}">
          更多分类 <span aria-hidden="true">${state.ledgerFilterExpanded ? "收起" : "展开"}</span>
        </button>
      ` : ""}
    </div>
    ${otherCategories.length ? `
      <div class="${panelClasses}">
        <div class="filter-popover-section">
          <div class="filter-popover-title">常用分类</div>
          <div class="filter-popover-grid">
            ${primaryCategories.map((category) => filterButton(category)).join("")}
          </div>
        </div>
        <div class="filter-popover-section">
          <div class="filter-popover-title">其他分类</div>
          <div class="filter-popover-grid">
            ${otherCategories.map((category) => filterButton(category)).join("")}
          </div>
        </div>
      </div>
    ` : ""}
  `;
}

function renderTransactions() {
  let transactions = scopedTransactions(state.period);
  if (state.filter !== "all") transactions = transactions.filter((tx) => (tx.category || "uncategorized") === state.filter);

  const totalPages = Math.max(1, Math.ceil(transactions.length / ledgerPageSize));
  state.ledgerPage = Math.min(Math.max(state.ledgerPage, 1), totalPages);
  const start = (state.ledgerPage - 1) * ledgerPageSize;
  const pageTransactions = transactions.slice(start, start + ledgerPageSize);

  $("transactionList").innerHTML = transactions.length
    ? pageTransactions
        .map((tx) => {
          const title = tx.merchant || tx.product || "未知商户";
          const thing = tx.thing || tx.product || "未识别消费内容";
          const method = tx.payment_method || "未知支付方式";
          const source = `${paymentLabel(tx.payment_app)} | ${method}`;
          return `
            <div class="transaction-item" data-motion-card>
              <div class="transaction-time">${escapeHtml(displayDate(tx.paid_at))}</div>
              <div>
                <div class="transaction-title">${escapeHtml(title)}</div>
                <div class="transaction-meta">${escapeHtml(thing)}</div>
              </div>
              <div class="transaction-chip">${escapeHtml(categoryLabel(tx.category))}</div>
              <div class="transaction-source">${escapeHtml(source)}</div>
              <div class="transaction-amount">${escapeHtml(formatMoney(tx.amount))}</div>
            </div>
          `;
        })
        .join("")
    : `<div class="empty-state">当前筛选没有交易。</div>`;

  $("ledgerPagination").innerHTML = transactions.length > ledgerPageSize
    ? `
      <div class="pagination-summary">共 ${transactions.length} 条 | 第 ${state.ledgerPage} / ${totalPages} 页</div>
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

function addMessage(role, text, options = {}) {
  const shouldSave = options.save !== false;
  const container = $("chatMessages");
  const node = document.createElement("div");
  node.className = `message ${role}`;
  if (options.shiny) {
    node.classList.add("thinking-message");
    node.innerHTML = `<span class="shiny-text">${escapeHtml(text)}</span>`;
  } else {
    if (options.periodTag) {
      const chip = document.createElement("span");
      chip.className = "period-chip";
      chip.textContent = options.periodTag;
      node.appendChild(chip);
    }
    const body = document.createElement("div");
    body.className = "message-body";
    setMessageContent(body, role, text, options);
    node.appendChild(body);
  }
  container.appendChild(node);
  container.scrollTop = container.scrollHeight;
  if (shouldSave && (role === "user" || role === "agent")) {
    state.chatHistory.push({
      role: role === "agent" ? "assistant" : "user",
      content: text,
    });
    state.chatHistory = state.chatHistory.slice(-12);
  }
  return node;
}

async function askCfoAgent(question, history) {
  const response = await fetch("./api/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      message: question,
      period: state.period,
      history,
      budgets: state.budgets,
    }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.answer || `请求失败：HTTP ${response.status}`);
  return data.answer || "DeepSeek 没有返回可展示内容。";
}

async function submitQuestion(question) {
  if (state.chatBusy) return;
  state.chatBusy = true;
  const priorHistory = [...state.chatHistory];
  addMessage("user", question, { split: true, periodTag: periodLabel(state.period) });
  const thinkingNode = addMessage("agent", "DeepSeek 正在读取账本并生成回答...", { save: false, shiny: true });
  try {
    const answer = await askCfoAgent(question, priorHistory);
    thinkingNode.classList.remove("thinking-message");
    setMessageContent(thinkingNode, "agent", answer, { split: true });
    state.chatHistory.push({ role: "assistant", content: answer });
    state.chatHistory = state.chatHistory.slice(-12);
  } catch (error) {
    const fallback = `对话请求失败：${error.message}`;
    thinkingNode.classList.remove("thinking-message");
    setMessageContent(thinkingNode, "agent", fallback, { split: true });
    state.chatHistory.push({ role: "assistant", content: fallback });
    state.chatHistory = state.chatHistory.slice(-12);
  } finally {
    state.chatBusy = false;
  }
}

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
}

function renderSyncItems(items = []) {
  $("syncItemList").innerHTML = items.length
    ? items
        .map((item) => `
          <div class="sync-item">
            <div>
              <div class="sync-item-title">${escapeHtml(item.merchant || "未知商户")}</div>
              <div class="sync-item-meta">${escapeHtml(displayDate(item.paid_at))} | ${escapeHtml(item.transaction_uid || item.uid || "未生成交易号")}</div>
            </div>
            <div>
              <div class="sync-item-amount">${escapeHtml(formatMoney(item.amount))}</div>
              <div class="sync-item-category">${escapeHtml(categoryLabel(item.category))}</div>
            </div>
          </div>
        `)
        .join("")
    : `<div class="empty-state">本次没有处理到新的账单附件。</div>`;
}

function resetSyncModal() {
  setSyncModalState("idle", "等待开始", "将扫描未读账单邮件，成功处理后自动标记已读。");
  renderSyncMetrics();
  $("syncFinishedAt").textContent = "未开始";
  $("syncItemList").innerHTML = `<div class="empty-state">点击下方按钮后开始同步。</div>`;
}

async function syncMailData() {
  if (state.syncBusy) return;
  state.syncBusy = true;
  $("startSyncButton").disabled = true;
  $("openSyncModal").disabled = true;
  $("startSyncButton").textContent = "同步中...";
  setSyncModalState("running", "正在连接邮箱并扫描未读账单", "同步期间请保持当前 Web 服务运行。");
  renderSyncMetrics({ candidate_count: "--", matched_messages: "--", processed_attachments: "--", new_transactions: "--" });
  $("syncFinishedAt").textContent = "进行中";
  $("syncItemList").innerHTML = `<div class="empty-state">正在读取邮箱与 OCR 账单截图...</div>`;

  try {
    const response = await fetch("./api/sync-mail", { method: "POST" });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.answer || `同步请求失败：HTTP ${response.status}`);
    }

    await loadSnapshot();
    renderAll();
    if (!$("trendModal").hidden) renderTrendModal();
    window.refreshCfoMotion?.();

    renderSyncMetrics(payload);
    renderSyncItems(payload.items || []);
    $("syncFinishedAt").textContent = payload.finished_at ? displayDateTime(payload.finished_at) : "刚刚";
    const title = payload.new_transactions > 0
      ? `已同步 ${payload.new_transactions} 笔新交易`
      : "没有发现新的未读账单";
    const meta = `扫描 ${payload.candidate_count} 封候选邮件，命中 ${payload.matched_messages} 封，处理 ${payload.processed_attachments} 个附件，用时 ${payload.duration_seconds}s。`;
    setSyncModalState("success", title, meta);
  } catch (error) {
    renderSyncMetrics({ candidate_count: 0, matched_messages: 0, processed_attachments: 0, new_transactions: 0 });
    $("syncFinishedAt").textContent = "失败";
    $("syncItemList").innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    setSyncModalState("error", "邮箱同步没有完成", error.message);
  } finally {
    state.syncBusy = false;
    $("startSyncButton").disabled = false;
    $("openSyncModal").disabled = false;
    $("startSyncButton").textContent = "重新同步";
  }
}

function renderAll() {
  renderHeader();
  renderMetrics();
  renderCoreNodes();
  renderDecisionFeed();
  renderCategoryStack();
  renderFilters();
  renderTransactions();
}

function setActiveNav(sectionId) {
  document.querySelectorAll("[data-nav-section]").forEach((item) => {
    const active = item.dataset.navSection === sectionId;
    item.classList.toggle("active", active);
    if (active) {
      item.setAttribute("aria-current", "true");
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

  const railHeight = document.querySelector(".command-rail")?.getBoundingClientRect().height || 0;
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

function wireInteractions() {
  $("openTrendModal").addEventListener("click", () => {
    openModal("trendModal");
  });

  $("openBudgetSettings").addEventListener("click", () => {
    openModal("budgetModal");
  });

  $("openSyncModal").addEventListener("click", () => {
    openModal("syncModal");
    syncMailData();
  });

  $("startSyncButton").addEventListener("click", () => {
    syncMailData();
  });

  document.querySelectorAll("[data-modal-close]").forEach((button) => {
    button.addEventListener("click", () => closeModal(button.dataset.modalClose));
  });

  document.querySelectorAll(".modal-backdrop").forEach((backdrop) => {
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop) closeModal(backdrop.id);
    });
  });

  $("trendModeControl").addEventListener("click", (event) => {
    const button = event.target.closest("[data-trend-mode]");
    if (!button) return;
    state.trendMode = button.dataset.trendMode;
    renderTrendModal();
  });

  $("trendChart").addEventListener("pointermove", (event) => {
    const target = event.target.closest("[data-trend-index]");
    const tooltip = $("trendTooltip");
    if (!target) {
      tooltip.hidden = true;
      return;
    }
    const item = state.activeTrendSeries[Number(target.dataset.trendIndex)];
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
    const pointerX = event.clientX - rect.left;
    const pointerY = event.clientY - rect.top;
    const margin = 10;
    const gap = 12;
    let left = pointerX + gap;
    let top = pointerY - tooltipRect.height - gap;

    if (left + tooltipRect.width > rect.width - margin) {
      left = pointerX - tooltipRect.width - gap;
    }

    if (top < margin) {
      top = pointerY + gap;
    }

    tooltip.style.left = `${clamp(left, margin, rect.width - tooltipRect.width - margin)}px`;
    tooltip.style.top = `${clamp(top, margin, rect.height - tooltipRect.height - margin)}px`;
    tooltip.style.visibility = "visible";
  });

  $("trendChart").addEventListener("pointerleave", () => {
    $("trendTooltip").hidden = true;
  });

  $("budgetForm").addEventListener("submit", (event) => {
    event.preventDefault();
    saveBudgets({
      day: Math.max(0, Number($("dayBudgetInput").value || 0)),
      week: Math.max(0, Number($("weekBudgetInput").value || 0)),
      month: Math.max(0, Number($("monthBudgetInput").value || 0)),
    });
    closeModal("budgetModal");
  });

  $("resetBudgetButton").addEventListener("click", () => {
    saveBudgets({ ...defaultBudgets });
    renderBudgetForm();
  });

  window.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!$("trendModal").hidden) closeModal("trendModal");
    if (!$("budgetModal").hidden) closeModal("budgetModal");
    if (!$("syncModal").hidden) closeModal("syncModal");
  });

  document.querySelectorAll(".period-btn").forEach((button) => {
    button.addEventListener("click", () => {
      state.period = button.dataset.period;
      state.ledgerPage = 1;
      document.querySelectorAll(".period-btn").forEach((item) => item.classList.toggle("active", item === button));
      renderAll();
      window.refreshCfoMotion?.({ scope: "global" });
    });
  });

  $("filterBar").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    if (button.dataset.filterAction === "toggle-more") {
      state.ledgerFilterExpanded = !state.ledgerFilterExpanded;
      renderFilters();
      window.refreshCfoMotion?.({ scope: "ledger", quiet: true });
      return;
    }
    if (!button.dataset.filter) return;
    state.filter = button.dataset.filter;
    state.ledgerFilterExpanded = false;
    state.ledgerPage = 1;
    renderFilters();
    renderTransactions();
    window.refreshCfoMotion?.({ scope: "ledger" });
  });

  $("ledgerPagination").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button || button.disabled || !button.dataset.pageAction) return;
    if (button.dataset.pageAction === "prev") state.ledgerPage -= 1;
    if (button.dataset.pageAction === "next") state.ledgerPage += 1;
    renderTransactions();
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

  document.querySelectorAll(".quick-prompts button").forEach((button) => {
    button.addEventListener("click", () => {
      const question = button.dataset.question;
      submitQuestion(question);
    });
  });

  $("chatForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = $("chatInput");
    const question = input.value.trim();
    if (!question) return;
    input.value = "";
    submitQuestion(question);
  });

  document.querySelectorAll(".nav-item").forEach((item) => {
    item.addEventListener("click", () => {
      if (item.dataset.navSection) setActiveNav(item.dataset.navSection);
    });
  });

  wireScrollSpy();
}

async function loadSnapshot() {
  const response = await fetch("./data.json", { cache: "no-store" });
  if (!response.ok) throw new Error(`data.json 加载失败：HTTP ${response.status}`);
  const data = await response.json();
  state.generatedAt = data.generated_at || null;
  state.transactions = (data.transactions || []).sort((a, b) => parseDate(b.paid_at) - parseDate(a.paid_at));
}

async function boot() {
  if (window.location.protocol === "file:") {
    document.body.innerHTML = `
      <main style="padding:24px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#070d0b;color:#e9fff9;min-height:100dvh">
        <h1>请通过本地服务打开</h1>
        <p style="color:#88a29b;line-height:1.7">当前是 file:// 页面，浏览器会阻止读取 data.json。请打开 <a style="color:#9cffea" href="http://localhost:8091/">http://localhost:8091/</a>。</p>
      </main>
    `;
    return;
  }

  const dataReady = loadSnapshot().then(() => {
    renderAll();
    if (!$("trendModal").hidden) renderTrendModal();
  });
  window.cfoDataReady = dataReady;

  addMessage("agent", "财务大脑已同步当前账本。你可以问今日支出、本月最大项、预算使用率，或者最近外卖/奶茶频率。");
  wireInteractions();
  window.initCfoMotion?.();
  await dataReady;

  window.setInterval(async () => {
    try {
      await loadSnapshot();
      renderAll();
      if (!$("trendModal").hidden) renderTrendModal();
      window.refreshCfoMotion?.({ quiet: true });
    } catch (error) {
      console.warn("snapshot refresh failed", error);
    }
  }, 30000);
}

boot().catch((error) => {
  document.body.innerHTML = `<main style="padding:24px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#070d0b;color:#e9fff9;min-height:100dvh"><h1>数据加载失败</h1><p>${escapeHtml(error.message)}</p></main>`;
});
