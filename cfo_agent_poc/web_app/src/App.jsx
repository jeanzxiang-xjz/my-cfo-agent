import openingImage from "../assets/opening-cfo-illustration.webp";
import { ownerName } from "./owner.js";
import { PHOSPHOR_ICONS } from "./phosphor-icons.js";

// 首屏静态骨架。所有 id / data-* 属性都是 legacy-controller.js 的渲染契约，
// 改名前请同步检查 src/legacy-controller.js。

// 开场插画必须先解码完成，否则擦除动画会先播、图后跳出来。
export const CRITICAL_IMAGE_URLS = [openingImage];

function AppLoadingScreen() {
  return (
    <div className="app-loading-screen" aria-hidden="true">
      <div className="loading-mark">
        <span className="loading-mark-bar" />
        <span className="loading-mark-bar" />
        <span className="loading-mark-bar" />
      </div>
    </div>
  );
}

// 大字标第一行默认是「Jeanz」（等宽字体约 3em 宽）。换成用户称呼后按宽度等比缩小，
// 汉字按 1em、其余按 0.6em 估宽；缩到下限还放不下就截断加省略号。
const OPENING_NAME_FIT_EM = 3.6;
const OPENING_NAME_MIN_SCALE = 0.36;
const CJK_CHAR = /[⺀-鿿豈-﫿＀-￯]/;

function openingName() {
  const name = ownerName() || "Jeanz";
  const maxWidth = OPENING_NAME_FIT_EM / OPENING_NAME_MIN_SCALE;
  let text = "";
  let width = 0;
  for (const char of name) {
    const charWidth = CJK_CHAR.test(char) ? 1 : 0.6;
    if (width + charWidth > maxWidth) {
      text += "…";
      width += 0.6;
      break;
    }
    text += char;
    width += charWidth;
  }
  return {
    text,
    cjk: CJK_CHAR.test(text),
    scale: Math.max(OPENING_NAME_MIN_SCALE, Math.min(1, OPENING_NAME_FIT_EM / width)),
  };
}

/**
 * 开场页：左侧字标（称呼 + CFO）、右侧线稿插画取景框。
 * 可点击 / Esc 跳过，一次会话只播一次，数据就绪或 1.2s 超时后收起。
 */
function OpeningOverlay() {
  const name = openingName();
  return (
    <div className="opening-overlay" role="presentation">
      <div className="opening-frame">
        <span className="opening-rule opening-rule-top" aria-hidden="true" />
        <div className="opening-content">
          <div className="opening-copy">
            <p className="opening-kicker">PRIVATE CASHFLOW INTELLIGENCE</p>
            <div className="opening-title">
              <span>
                <i className={name.cjk ? "opening-name is-cjk" : "opening-name"} style={{ fontSize: `${name.scale}em` }}>
                  {name.text}
                </i>
              </span>
              <span>
                <i>CFO</i>
              </span>
            </div>
            <p className="opening-tagline">让每一笔，都变成更好的选择</p>
            <span className="opening-scan" aria-hidden="true" />
            <p className="opening-subline">一个会记录、会分析、会提醒你的私人 CFO Agent</p>
          </div>
          <div className="opening-illustration-wrap">
            <span className="opening-illustration-glow" aria-hidden="true" />
            <img className="opening-illustration" src={openingImage} alt="" />
            <span className="opening-sweep" aria-hidden="true" />
          </div>
        </div>
        <span className="opening-rule opening-rule-bottom" aria-hidden="true" />
      </div>
      <button className="opening-skip" type="button" data-opening-skip>
        跳过 <kbd>Esc</kbd>
      </button>
    </div>
  );
}

/** Phosphor 图标（regular 字重）。图形在 phosphor-icons.js，线宽和填充在 styles.css 的 svg.ph 段。 */
function Ph({ name, className = "" }) {
  return (
    <svg
      className={className ? `ph ${className}` : "ph"}
      viewBox="0 0 256 256"
      aria-hidden="true"
      focusable="false"
      dangerouslySetInnerHTML={{ __html: PHOSPHOR_ICONS[name] }}
    />
  );
}

function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect x="0.75" y="0.75" width="30.5" height="30.5" rx="9" className="brand-mark-plate" />
      <path className="brand-mark-stroke" d="M21.5 11.2a6.6 6.6 0 1 0 0 9.6" />
      <path className="brand-mark-tick" d="M9 22.6h14" />
    </svg>
  );
}

function TopRail() {
  return (
    <header className="rail" id="top">
      <a className="brand" href="#main">
        <BrandMark />
        <span className="brand-text">
          <span className="brand-name">Jeanz CFO</span>
          <span className="brand-sub">私人财务大脑</span>
        </span>
      </a>

      <nav className="rail-nav" aria-label="页面区块">
        <a className="nav-item is-active" href="#chat" data-nav-section="chat" aria-current="location">
          对话
        </a>
        <a className="nav-item" href="#signals" data-nav-section="signals">
          分析
        </a>
        <a className="nav-item" href="#ledger" data-nav-section="ledger">
          账本
        </a>
      </nav>

      <div className="rail-tail">
        <div className="period-control" role="radiogroup" aria-label="统计周期">
          <span className="period-thumb" aria-hidden="true" />
          <button className="period-btn active" data-period="today" type="button" role="radio" aria-checked="true" tabIndex={0}>
            今日
          </button>
          <button className="period-btn" data-period="week" type="button" role="radio" aria-checked="false" tabIndex={-1}>
            本周
          </button>
          <button className="period-btn" data-period="month" type="button" role="radio" aria-checked="false" tabIndex={-1}>
            本月
          </button>
          <button className="period-btn" data-period="all" type="button" role="radio" aria-checked="false" tabIndex={-1}>
            全部
          </button>
          <button
            id="customPeriodBtn"
            className="period-btn is-custom"
            data-period="custom"
            type="button"
            role="radio"
            aria-checked="false"
            aria-haspopup="dialog"
            aria-expanded="false"
            tabIndex={-1}
          >
            <Ph name="calendar-dots" className="period-btn-icon" />
            <span className="period-btn-label" id="customPeriodLabel">
              自定义
            </span>
          </button>
          <button id="periodClear" className="period-clear" type="button" aria-label="清除自定义区间，回到预设周期" hidden>
            <Ph name="x-circle" />
          </button>
        </div>

        <div className="rail-actions">
          <button id="openTrendModal" className="rail-action" type="button" aria-label="现金流趋势" title="现金流趋势">
            <Ph name="chart-line-up" />
            <span className="rail-action-text">趋势</span>
          </button>
          <button id="openCaptureModal" className="rail-action" type="button" aria-label="记一笔：连接 iPhone 或上传截图" title="记一笔">
            <Ph name="plus-circle" />
            <span className="rail-action-text">记一笔</span>
          </button>
          <button id="openBudgetSettings" className="rail-action rail-action-icon" type="button" aria-label="预算配置" title="预算配置">
            <Ph name="sliders-horizontal" />
          </button>
          <button id="openAccountModal" className="rail-action rail-action-icon" type="button" aria-label="账户" title="账户">
            <Ph name="user-circle" />
          </button>
        </div>
      </div>
    </header>
  );
}

/** 首屏：左侧是当期数字，右侧是 CFO 对话。 */
function OverviewHero() {
  return (
    <section className="hero" id="chat" aria-labelledby="periodLabel">
      <article className="panel hero-figure" aria-label="当期概览">
        <div className="hero-figure-top">
          <p className="eyebrow agent-eyebrow">当前周期</p>
          <h1 className="hero-title" id="periodLabel">
            今日净支出
          </h1>
          <div className="figure-row">
            <p className="figure" id="coreAmount">
              <span className="skeleton skeleton-figure" aria-hidden="true" />
              <span className="visually-hidden">读取中</span>
            </p>
            <p className="figure-delta" id="coreDelta" hidden />
          </div>
          <p className="figure-meta" id="primaryMeta">
            <span className="skeleton skeleton-line" aria-hidden="true" />
          </p>
        </div>

        <div className="hero-budget" id="heroBudget">
          <div className="hero-budget-head">
            <span className="micro-label" id="heroBudgetLabel">
              日预算
            </span>
            <span className="hero-budget-value" id="heroBudgetValue">
              --
            </span>
          </div>
          <div className="meter" role="progressbar" aria-labelledby="heroBudgetLabel" aria-valuemin={0} aria-valuemax={100} aria-valuenow={0} id="heroBudgetMeter">
            <span className="meter-fill" id="heroBudgetFill" />
            <span className="meter-tick" aria-hidden="true" />
          </div>
          <p className="hero-budget-foot" id="heroBudgetFoot">
            设置预算后可在这里看到使用进度。
          </p>
        </div>

        <button className="hero-spark" id="heroSpark" type="button" aria-label="查看现金流趋势">
          <span id="heroTrendContent" className="hero-trend-content">
            <span className="hero-spark-head">
              <span className="micro-label">现金流</span>
              <span className="hero-spark-cta">
                查看趋势
                <Ph name="caret-right" />
              </span>
            </span>
            {/*
              走势徽标：抽象波形柱，不吃数据。高度包络是设计出来的——平缓起、
              中段主峰、尾部收在中位；刻意不做成向右上方的爬升，记账产品里那读作「花得更多」。
              每根柱是一条 non-scaling-stroke 的 line：容器横向被拉伸 3 倍多，
              用 stroke 才能保证柱宽和圆头在任何宽度下都不变形。
            */}
            <span className="hero-spark-chart" id="heroSparkChart" aria-hidden="true">
              {/*
                viewBox 横向从 0.89 取到 139.11：首末两根柱的外缘（中心 2.19 / 137.81，柱宽 2.6）。
                柱阵正好铺满内容宽度，左右缘和上方「现金流」「查看趋势 ›」对齐，不再往里缩一截。
              */}
              <svg className="spark-wave-svg" viewBox="0.89 0 138.22 46" preserveAspectRatio="none" focusable="false">
                <defs>
                  <linearGradient id="sparkWaveStroke" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="140" y2="0">
                    <stop className="spark-wave-stop-dim" offset="0" />
                    <stop className="spark-wave-stop-mid" offset="0.55" />
                    <stop className="spark-wave-stop-lit" offset="1" />
                  </linearGradient>
                </defs>
                <g className="spark-wave-bars">
                  <line x1="2.19" y1="45" x2="2.19" y2="33.02" />
                  <line x1="6.56" y1="45" x2="6.56" y2="31.64" />
                  <line x1="10.94" y1="45" x2="10.94" y2="30.59" />
                  <line x1="15.31" y1="45" x2="15.31" y2="30" />
                  <line x1="19.69" y1="45" x2="19.69" y2="29.65" />
                  <line x1="24.06" y1="45" x2="24.06" y2="29.05" />
                  <line x1="28.44" y1="45" x2="28.44" y2="27.81" />
                  <line x1="32.81" y1="45" x2="32.81" y2="25.89" />
                  <line x1="37.19" y1="45" x2="37.19" y2="23.67" />
                  <line x1="41.56" y1="45" x2="41.56" y2="21.81" />
                  <line x1="45.94" y1="45" x2="45.94" y2="20.81" />
                  <line x1="50.31" y1="45" x2="50.31" y2="20.78" />
                  <line x1="54.69" y1="45" x2="54.69" y2="21.29" />
                  <line x1="59.06" y1="45" x2="59.06" y2="21.57" />
                  <line x1="63.44" y1="45" x2="63.44" y2="20.86" />
                  <line x1="67.81" y1="45" x2="67.81" y2="18.8" />
                  <line x1="72.19" y1="45" x2="72.19" y2="15.64" />
                  <line x1="76.56" y1="45" x2="76.56" y2="12.18" />
                  <line x1="80.94" y1="45" x2="80.94" y2="9.49" />
                  <line x1="85.31" y1="45" x2="85.31" y2="8.47" />
                  <line x1="89.69" y1="45" x2="89.69" y2="9.48" />
                  <line x1="94.06" y1="45" x2="94.06" y2="12.22" />
                  <line x1="98.44" y1="45" x2="98.44" y2="15.81" />
                  <line x1="102.81" y1="45" x2="102.81" y2="19.21" />
                  <line x1="107.19" y1="45" x2="107.19" y2="21.6" />
                  <line x1="111.56" y1="45" x2="111.56" y2="22.62" />
                  <line x1="115.94" y1="45" x2="115.94" y2="22.43" />
                  <line x1="120.31" y1="45" x2="120.31" y2="21.58" />
                  <line x1="124.69" y1="45" x2="124.69" y2="20.65" />
                  <line x1="129.06" y1="45" x2="129.06" y2="20.12" />
                  <line x1="133.44" y1="45" x2="133.44" y2="20.15" />
                  <line x1="137.81" y1="45" x2="137.81" y2="20.66" />
                </g>
                <line className="spark-wave-base" x1="0.89" y1="45.5" x2="139.11" y2="45.5" />
              </svg>
            </span>
          </span>

          <span id="heroProfileContent" className="hero-profile-content" hidden>
            <span className="hero-profile-mark" aria-hidden="true">
              <Ph name="sparkle" />
            </span>
            <span className="hero-profile-copy">
              <strong>你的钱，藏着一种生活流派</strong>
              <small id="heroProfileMeta">正在整理全部消费记录</small>
            </span>
            <span className="hero-profile-action">
              <span id="heroProfileActionLabel">生成画像</span>
              <Ph name="caret-right" />
            </span>
          </span>
        </button>
      </article>

      <article id="heroChat" className="panel hero-chat" aria-label="CFO 对话">
        <header className="chat-head">
          <div className="chat-head-row">
            <div className="chat-head-title">
              <span className="pulse-dot" aria-hidden="true" />
              <h2>与 CFO Agent 对话</h2>
            </div>
            <div className="chat-head-actions">
              <button id="copyLastAnswerButton" className="chat-icon-action" type="button" aria-label="复制最近一条 CFO 回答" title="复制最近回答" hidden>
                <Ph name="copy" />
              </button>
              <button id="clearChatButton" className="chat-icon-action" type="button" aria-label="清空当前会话" title="清空会话">
                <Ph name="trash" />
              </button>
              <button id="expandChatButton" className="chat-mode-action" type="button" aria-label="展开对话" aria-expanded="false" aria-controls="heroChat" title="展开对话">
                <Ph name="corners-out" />
                <span>展开对话</span>
              </button>
              <button id="closeChatExpandButton" className="chat-mode-action" type="button" aria-label="退出展开对话" title="退出展开对话" hidden>
                <Ph name="corners-in" />
                <span>退出展开</span>
              </button>
            </div>
          </div>
          <p id="headerSummary" className="chat-head-summary">
            正在读取账本快照。
          </p>
        </header>

        <div className="chat-message-stage">
          <div id="chatMessages" className="chat-messages" role="log" aria-live="polite" aria-label="对话记录" tabIndex={0} />
          <button id="chatLatestButton" className="chat-latest-button" type="button" title="回到最新回答" hidden>
            <Ph name="arrow-line-down" />
            <span>回到最新</span>
          </button>
        </div>

        <div className="chat-foot">
          {/* 三类问题共用一条轨道：分段切换在左、当前这一类的胶囊在中、该类专属动作在右。
              对话面板纵向空间紧张（.hero-chat 是定高 grid，这里多一像素就从消息区扣一像素），
              所以三类不并排、不换行——任何视口下都恒定一行，窄屏由轨道自己横向滚。 */}
          <div className="prompt-rail">
            <div className="prompt-tabs" role="tablist" aria-label="快捷提问分类">
              <button
                id="promptTabGuess"
                className="prompt-tab is-guess"
                type="button"
                role="tab"
                data-prompt-tab="guess"
                aria-selected="true"
                aria-controls="promptTrackGuess"
              >
                <Ph name="sparkle" />
                <span className="prompt-tab-text">猜你想问</span>
              </button>
              <button
                id="promptTabPreset"
                className="prompt-tab"
                type="button"
                role="tab"
                data-prompt-tab="preset"
                aria-selected="false"
                aria-controls="promptTrackPreset"
                tabIndex={-1}
              >
                <span className="prompt-tab-text">常用</span>
              </button>
              <button
                id="promptTabMine"
                className="prompt-tab"
                type="button"
                role="tab"
                data-prompt-tab="mine"
                aria-selected="false"
                aria-controls="promptTrackMine"
                tabIndex={-1}
              >
                <span className="prompt-tab-text">我的</span>
              </button>
            </div>

            {/* 这个类名不能改：updateQuickPrompts 与 setChatBusy 都靠 .quick-prompts button
                找胶囊。分段与右侧动作刻意留在它外面，这样生成回答时胶囊置灰、切类和管理仍可用。 */}
            <div className="quick-prompts">
              <div
                id="promptTrackGuess"
                className="prompt-track"
                data-track="guess"
                role="tabpanel"
                aria-labelledby="promptTabGuess"
                aria-live="polite"
              >
                <span className="visually-hidden">这些问题按你当前选中的时段，从你的账本里挑出来</span>
                <span id="aiPromptList" className="ai-list" />
              </div>

              <div
                id="promptTrackPreset"
                className="prompt-track"
                data-track="preset"
                role="tabpanel"
                aria-labelledby="promptTabPreset"
                hidden
              >
                <button data-prompt-key="spend" data-question="我今天花了多少钱？" type="button">
                  今日支出
                </button>
                <button data-prompt-key="largest" data-question="今天最大的支出是什么？" type="button">
                  最大支出
                </button>
                <button data-prompt-key="analysis" data-question="分析下我今天的消费情况" type="button">
                  消费分析
                </button>
                <button data-prompt-key="takeout" data-question="我今天外卖点得多吗？" type="button">
                  外卖频率
                </button>
                <button data-prompt-key="budget" data-question="今日预算使用率是多少？" type="button">
                  预算状态
                </button>
              </div>

              <div
                id="promptTrackMine"
                className="prompt-track"
                data-track="mine"
                role="tabpanel"
                aria-labelledby="promptTabMine"
                aria-live="polite"
                hidden
              />
            </div>

            <div className="prompt-rail-action">
              <button id="rerollPrompts" className="rail-icon-button" type="button" aria-label="换一批问题" title="换一批">
                <Ph name="arrows-clockwise" />
              </button>
              <button
                id="managePrompts"
                className="rail-icon-button"
                type="button"
                data-open-modal="promptModal"
                aria-label="管理我的常问"
                title="管理我的常问"
                hidden
              >
                <Ph name="plus" />
              </button>
            </div>
          </div>

          <form id="chatForm" className="chat-form" noValidate>
            <label className="visually-hidden" htmlFor="chatInput">
              向 CFO Agent 提问
            </label>
            <div className="chat-input-row">
              <input
                id="chatInput"
                type="text"
                autoComplete="off"
                enterKeyHint="send"
                maxLength={600}
                placeholder="问点什么，比如「这周奶茶花了多少」"
                aria-describedby="chatHint"
              />
              <button type="submit" className="chat-send" data-label-idle="发送" data-label-busy="生成中">
                <span className="chat-send-text">发送</span>
                <Ph name="arrow-right" />
              </button>
            </div>
            <p className="chat-hint" id="chatHint">
              回车发送 · <kbd>/</kbd> 聚焦 · 数据仅来自本机账本
            </p>
          </form>
        </div>
      </article>
      <div id="chatExpandPlaceholder" className="chat-expand-placeholder" hidden aria-hidden="true" />
    </section>
  );
}

function IntelligencePanel() {
  return (
    <section className="section intelligence-panel" id="signals" aria-labelledby="signalsTitle">
      <header className="section-head">
        <div className="section-head-copy">
          <div className="section-title-line">
            <span className="section-title-mark" aria-hidden="true">
              <Ph name="eye" />
            </span>
            <h2 id="signalsTitle">关键观察</h2>
          </div>
          <p id="coreNarrative">等待 Agent 建立当前消费画像。</p>
        </div>
        <div className="section-head-actions">
          <span className="state-chip" id="analysisState">
            Learning
          </span>
        </div>
      </header>

      <div className="stat-row" aria-label="核心指标">
        <div className="stat">
          <span className="micro-label" id="avgSpendLabel">
            日均支出
          </span>
          <strong id="avgDailySpend">--</strong>
        </div>
        <div className="stat">
          <span className="micro-label">消费笔数</span>
          <strong id="txnCount">--</strong>
        </div>
        <div className="stat">
          <span className="micro-label">最大单笔</span>
          <strong id="largestSpend">--</strong>
        </div>
        <div className="stat">
          <span className="micro-label">解析置信</span>
          <strong id="confidenceScore">--</strong>
        </div>
      </div>

      <div className="analysis-grid">
        <article className="panel analysis-feed" aria-labelledby="analysisTitle">
          <div className="mini-heading analysis-heading">
            <h3 id="analysisTitle">今日消费分析</h3>
            <span id="signalMeta">等待样本</span>
          </div>
          <p className="analysis-note">每条结论都能追到原始交易，或者直接交给 Agent 展开。</p>
          <div id="decisionFeed" className="decision-feed" />
        </article>

        <article className="panel category-console" aria-labelledby="categoryTitle">
          <div className="mini-heading">
            <h3 id="categoryTitle">支出去向</h3>
            <span id="categoryCount">--</span>
          </div>
          <div id="coreNodes" className="composition-body" />
          <div id="categoryStack" className="category-stack" />
        </article>
      </div>
    </section>
  );
}

function LedgerPanel() {
  return (
    <section className="section ledger-panel" id="ledger" aria-labelledby="ledgerTitle">
      <header className="section-head ledger-heading">
        <div className="section-head-copy">
          <div className="section-title-line">
            <span className="section-title-mark" aria-hidden="true">
              <Ph name="receipt" />
            </span>
            <h2 id="ledgerTitle">可追溯交易</h2>
          </div>
          <p>打开任意一笔，核查截图、OCR 与分类依据。</p>
        </div>
      </header>

      <div id="correctionQueue" className="correction-queue" aria-live="polite" hidden />

      <div id="filterBar" className="filter-bar" aria-label="分类筛选" />

      <div className="table-wrap">
        <table className="ledger-table">
          <caption className="visually-hidden">当前周期的交易明细</caption>
          <thead>
            <tr>
              <th scope="col">时间</th>
              <th scope="col">商户 / 内容</th>
              <th scope="col">分类</th>
              <th scope="col">渠道</th>
              <th scope="col" className="col-amount">
                <button
                  type="button"
                  id="ledgerAmountSort"
                  className="ledger-amount-sort"
                  data-sort-state="date"
                  aria-pressed="false"
                  aria-label="按金额从大到小排序"
                >
                  <span>金额</span>
                  <Ph name="caret-up-down" />
                </button>
              </th>
            </tr>
          </thead>
          <tbody id="transactionList" />
        </table>
      </div>

      <div id="ledgerPagination" className="ledger-pagination" aria-label="交易分页" />
    </section>
  );
}

function SiteFooter() {
  return (
    <footer className="site-foot">
      <p className="site-foot-note">
        <span>本地记录</span>
        <span className="site-foot-note-separator" aria-hidden="true">/</span>
        <span>实时分析</span>
        <span className="site-foot-note-separator" aria-hidden="true">/</span>
        <span>受信访问</span>
      </p>
      <p className="site-foot-meta">
        <span id="footerGenerated">快照时间 --</span>
        <span aria-hidden="true">·</span>
        <a id="backToTopButton" href="#top">回到顶部</a>
      </p>
    </footer>
  );
}

function TrendModal() {
  return (
    <div id="trendModal" className="modal-backdrop" hidden>
      <section className="modal-shell trend-modal" role="dialog" aria-modal="true" aria-labelledby="trendTitle">
        <div className="modal-header trend-modal-header">
          <div className="trend-modal-heading">
            <h2 id="trendTitle">现金流趋势</h2>
            <p id="trendSubtitle">正在读取现金流曲线。</p>
          </div>
          <div className="trend-control" id="trendModeControl" role="radiogroup" aria-label="趋势周期">
            <button className="active" data-trend-mode="day" type="button" role="radio" aria-checked="true" tabIndex={0}>
              日
            </button>
            <button data-trend-mode="week" type="button" role="radio" aria-checked="false" tabIndex={-1}>
              周
            </button>
            <button data-trend-mode="month" type="button" role="radio" aria-checked="false" tabIndex={-1}>
              月
            </button>
          </div>
          <button className="modal-close" type="button" data-modal-close="trendModal" aria-label="关闭趋势弹窗">
            <Ph name="x" />
          </button>
        </div>

        <div className="trend-layout">
          <div className="trend-main">
            <div className="trend-chart-panel">
              <div id="trendChart" className="trend-chart" />
              <div id="trendTooltip" className="trend-tooltip" role="status" hidden />
            </div>
            {/* 柱子选「哪一期」，这里把那一期摊开：月 → 日历，周 → 七天，日 → 当天流水。 */}
            <section id="trendDetail" className="trend-detail" aria-label="所选时段的消费明细" />
          </div>

          <aside className="trend-aside" aria-label="预算与当日明细">
            <section className="trend-budget-panel" id="trendBudgetPanel" aria-label="预算状态">
              {/* 口径行：这块预算数字算的是哪一段时间。点柱子后跟着选中的那一期走。 */}
              <p className="budget-scope" aria-live="polite">
                <span className="budget-scope-dot" aria-hidden="true" />
                <span className="budget-scope-text" id="trendBudgetScopeText">
                  今日
                </span>
                <em className="budget-scope-state" id="trendBudgetScopeState">
                  进行中
                </em>
                <button className="budget-scope-reset" id="trendBudgetReset" type="button" hidden>
                  回到当前
                </button>
              </p>
              <div className="budget-kpi">
                <span id="trendBudgetLabel">月预算</span>
                <strong id="trendBudgetValue">--</strong>
              </div>
              <div className="budget-usage">
                <div className="budget-usage-head">
                  <span>使用率</span>
                  <strong id="trendBudgetPercent">--</strong>
                </div>
                <div className="meter">
                  <span className="meter-fill" id="trendBudgetProgress" />
                  <span className="meter-tick" aria-hidden="true" />
                </div>
              </div>
              <div className="budget-rest">
                <span id="trendBudgetRestLabel">还能花</span>
                <strong id="trendBudgetRemaining">--</strong>
                <div className="budget-rest-meta">
                  <span id="trendBudgetAverageLabel">日均可用</span>
                  <small id="trendBudgetAverage">--</small>
                </div>
              </div>
              <p className="budget-hint">
                预算可在
                <button type="button" className="link-button" data-open-modal="budgetModal">
                  预算配置
                </button>
                里调整。
              </p>
            </section>
            <section id="trendSidePanel" className="trend-side-panel" aria-label="当日明细" />
          </aside>
        </div>
      </section>
    </div>
  );
}

function CaptureModal() {
  return (
    <div id="captureModal" className="modal-backdrop" hidden>
      <section className="modal-shell sync-modal" role="dialog" aria-modal="true" aria-labelledby="captureTitle">
        <div className="modal-header">
          <div>
            <h2 id="captureTitle">记一笔</h2>
            <p>支付后在 iPhone 上点一下快捷指令，账单截图直接传进你的账本。</p>
          </div>
          <button className="modal-close" type="button" data-modal-close="captureModal" aria-label="关闭记一笔">
            <Ph name="x" />
          </button>
        </div>

        <p className="category-demo-notice" id="captureDemoNotice" hidden>
          演示模式不能连接 iPhone 或上传截图。
        </p>

        <div className="sync-body">
          <aside className="sync-guidance" aria-labelledby="captureGuidanceTitle">
            <span className="sync-guidance-icon" aria-hidden="true">
              <Ph name="receipt" />
            </span>
            <div>
              <strong id="captureGuidanceTitle">截图前，先打开账单详情页</strong>
              <p>确认金额、支付时间和商户都完整显示在屏幕上，再触发快捷指令。</p>
            </div>
          </aside>

          <section className="sync-state-card phone-link-card" id="phoneLinkCard" aria-labelledby="phoneLinkTitle">
            <span id="phoneLinkLabel" className="phone-link-label">
              <Ph name="link" />
              连接 iPhone
            </span>
            <strong id="phoneLinkTitle">读取中…</strong>
            <small id="phoneLinkMeta" />

            <div className="phone-link-secret" id="phoneLinkSecret" hidden>
              <code id="phoneLinkToken" />
              <button className="btn btn-quiet" type="button" id="copyUploadToken">
                <Ph name="copy" />
                复制密钥
              </button>
              <p>密钥只显示这一次，请现在复制。安装快捷指令时粘贴它；以后忘了就重新生成一个。</p>
            </div>

            <ol className="phone-link-steps">
              <li>生成上传密钥并复制</li>
              <li>安装「记一笔」快捷指令，按提示粘贴密钥</li>
              <li>支付后点开账单详情页，触发「记一笔」快捷指令即可</li>
            </ol>

            <div className="phone-link-url">
              <span>上传地址</span>
              <code id="phoneLinkUrl">--</code>
              <button className="link-button" type="button" id="copyUploadUrl">
                <Ph name="copy" />
                复制
              </button>
            </div>

            <div className="phone-link-actions">
              <a className="btn btn-primary" id="installShortcutLink" href="#" target="_blank" rel="noopener noreferrer" hidden>
                <Ph name="download-simple" />
                安装快捷指令
              </a>
              <button className="btn btn-quiet" type="button" id="rotateUploadToken">
                <Ph name="key" />
                <span data-button-label>生成上传密钥</span>
              </button>
              <button className="btn btn-quiet" type="button" id="revokeUploadToken" hidden>
                <Ph name="prohibit" />
                停用密钥
              </button>
            </div>
          </section>

          {/* 触发方式：很多人装好快捷指令后不知道怎么"点"它，这里列出四种常用入口 */}
          <section className="shortcut-triggers" aria-labelledby="shortcutTriggersTitle">
            <div className="shortcut-triggers-head">
              <h3 id="shortcutTriggersTitle">怎么触发快捷指令？</h3>
              <p>挑一种顺手的方式设置一次，以后停在账单详情页，一触即记。</p>
            </div>

            <ul className="shortcut-trigger-list">
              <li className="shortcut-trigger is-recommended">
                <div className="shortcut-trigger-head">
                  <span className="shortcut-trigger-icon">
                    <Ph name="action-button" />
                  </span>
                  <h4>按住左侧操作按钮</h4>
                  <span className="shortcut-trigger-badge">推荐</span>
                </div>
                <p>单手就能完成，不用离开账单页。</p>
                <ol className="shortcut-trigger-path" aria-label="设置路径">
                  <li>设置</li>
                  <li>操作按钮</li>
                  <li>快捷指令</li>
                  <li>记一笔</li>
                </ol>
                <small>iPhone 15 Pro 及更新机型</small>
              </li>

              <li className="shortcut-trigger">
                <div className="shortcut-trigger-head">
                  <span className="shortcut-trigger-icon">
                    <Ph name="hand-tap" />
                  </span>
                  <h4>轻点手机背面三下</h4>
                </div>
                <p>不占按键，没有操作按钮的机型也能用。</p>
                <ol className="shortcut-trigger-path" aria-label="设置路径">
                  <li>设置</li>
                  <li>无障碍</li>
                  <li>触控</li>
                  <li>轻点背面</li>
                  <li>轻点三下</li>
                  <li>记一笔</li>
                </ol>
                <small>iPhone 8 及更新机型</small>
              </li>

              <li className="shortcut-trigger">
                <div className="shortcut-trigger-head">
                  <span className="shortcut-trigger-icon">
                    <Ph name="record" />
                  </span>
                  <h4>长按辅助触控小圆点</h4>
                </div>
                <p>屏幕上常驻一个悬浮按钮，随手一按就触发。</p>
                <ol className="shortcut-trigger-path" aria-label="设置路径">
                  <li>设置</li>
                  <li>无障碍</li>
                  <li>触控</li>
                  <li>辅助触控</li>
                  <li>自定操作</li>
                  <li>长按</li>
                  <li>记一笔</li>
                </ol>
                <small>小圆点不会出现在截图里</small>
              </li>

              <li className="shortcut-trigger">
                <div className="shortcut-trigger-head">
                  <span className="shortcut-trigger-icon">
                    <Ph name="microphone" />
                  </span>
                  <h4>对 Siri 说「记一笔」</h4>
                </div>
                <p>腾不出手时用，快捷指令的名字就是口令。</p>
                <p className="shortcut-trigger-phrase">
                  嘿 Siri，<strong>记一笔</strong>
                </p>
                <small>无需额外设置，开启 Siri 即可</small>
              </li>
            </ul>
          </section>

          <div className="sync-log-panel">
            <div className="mini-heading">
              <h3>最近上传</h3>
              <span id="captureListMeta">--</span>
            </div>
            <div id="captureItemList" className="sync-item-list" />
          </div>

          <div className="sync-actions">
            <input id="captureFileInput" type="file" accept="image/png,image/jpeg" multiple hidden />
            <button id="pickCaptureFiles" className="btn btn-primary" type="button">
              <Ph name="upload-simple" />
              <span data-button-label>上传截图</span>
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

function BudgetModal() {
  return (
    <div id="budgetModal" className="modal-backdrop" hidden>
      <section className="modal-shell budget-modal" role="dialog" aria-modal="true" aria-labelledby="budgetTitle">
        <div className="modal-header">
          <div>
            <h2 id="budgetTitle">预算配置</h2>
            <p>日、周、月预算会同时用于趋势弹窗和 CFO Agent 的对话上下文。</p>
          </div>
          <button className="modal-close" type="button" data-modal-close="budgetModal" aria-label="关闭预算配置">
            <Ph name="x" />
          </button>
        </div>

        <form id="budgetForm" className="budget-form" noValidate>
          <div className="field">
            <label htmlFor="dayBudgetInput">日预算</label>
            <div className="field-control">
              <span className="field-prefix" aria-hidden="true">
                ¥
              </span>
              <input id="dayBudgetInput" type="number" min="0" step="1" inputMode="decimal" aria-describedby="budgetError" />
            </div>
          </div>
          <div className="field">
            <label htmlFor="weekBudgetInput">周预算</label>
            <div className="field-control">
              <span className="field-prefix" aria-hidden="true">
                ¥
              </span>
              <input id="weekBudgetInput" type="number" min="0" step="1" inputMode="decimal" aria-describedby="budgetError" />
            </div>
          </div>
          <div className="field">
            <label htmlFor="monthBudgetInput">月预算</label>
            <div className="field-control">
              <span className="field-prefix" aria-hidden="true">
                ¥
              </span>
              <input id="monthBudgetInput" type="number" min="0" step="1" inputMode="decimal" aria-describedby="budgetError" />
            </div>
          </div>

          <p className="form-error" id="budgetError" role="alert" hidden />

          <div className="budget-actions">
            <button id="resetBudgetButton" className="btn btn-quiet" type="button">
              恢复默认
            </button>
            <button className="btn btn-primary" type="submit">
              保存配置
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function AccountModal() {
  return (
    <div id="accountModal" className="modal-backdrop" hidden>
      <section className="modal-shell account-modal" role="dialog" aria-modal="true" aria-labelledby="accountTitle">
        <div className="modal-header">
          <div>
            <h2 id="accountTitle">账户</h2>
            <p id="accountSubtitle">你的账本只属于这个账户，其他人看不到。</p>
          </div>
          <button className="modal-close" type="button" data-modal-close="accountModal" aria-label="关闭账户">
            <Ph name="x" />
          </button>
        </div>

        <p className="category-demo-notice" id="accountDemoNotice" hidden>
          演示模式没有账户，以下设置不可修改。
        </p>

        <div className="account-body">
          <form id="accountProfileForm" className="account-section" noValidate>
            <h3 className="account-section-title">基本信息</h3>
            <div className="field">
              <span className="field-label">邮箱</span>
              <p className="account-readonly" id="accountEmailValue" />
            </div>
            <div className="field">
              <label htmlFor="accountDisplayNameInput">称呼</label>
              <div className="field-control">
                <input id="accountDisplayNameInput" type="text" maxLength={20} autoComplete="nickname" aria-describedby="accountProfileError" />
              </div>
            </div>
            <p className="form-error" id="accountProfileError" role="alert" hidden />
            <div className="account-actions">
              <button className="btn btn-primary" type="submit">
                保存称呼
              </button>
            </div>
          </form>

          <form id="accountPasswordForm" className="account-section" noValidate>
            <h3 className="account-section-title">修改密码</h3>
            <div className="field">
              <label htmlFor="accountCurrentPassword">当前密码</label>
              <div className="field-control">
                <input id="accountCurrentPassword" type="password" autoComplete="current-password" aria-describedby="accountPasswordError" />
              </div>
            </div>
            <div className="field">
              <label htmlFor="accountNewPassword">新密码</label>
              <div className="field-control">
                <input id="accountNewPassword" type="password" autoComplete="new-password" placeholder="至少 8 位" aria-describedby="accountPasswordError" />
              </div>
            </div>
            <p className="form-error" id="accountPasswordError" role="alert" hidden />
            <div className="account-actions">
              <button className="btn btn-quiet" type="submit">
                修改密码
              </button>
            </div>
          </form>

          <section id="accountAdminSection" className="account-section" aria-labelledby="accountInviteTitle" hidden>
            <h3 className="account-section-title" id="accountInviteTitle">
              邀请码
            </h3>
            <p className="account-hint">新用户注册时需要填写。每个邀请码只能用一次，14 天内有效。</p>
            <ul id="accountInviteList" className="invite-list" />
            <div className="account-actions">
              <button id="createInviteButton" className="btn btn-quiet" type="button">
                生成邀请码
              </button>
            </div>
          </section>
        </div>

        <form id="accountLogoutForm" className="account-footer" method="post" action="./api/v1/logout">
          <button className="btn btn-quiet" type="submit">
            退出登录
          </button>
        </form>
      </section>
    </div>
  );
}

function RangePickerModal() {
  return (
    <div id="rangeModal" className="modal-backdrop" hidden>
      <section className="modal-shell range-modal" role="dialog" aria-modal="true" aria-labelledby="rangeTitle">
        <div className="modal-header">
          <div>
            <h2 id="rangeTitle">选择时间区间</h2>
            <p>选定后，首屏数字、关键观察、支出去向、账本与提问都按这段时间重算。</p>
          </div>
          <button className="modal-close" type="button" data-modal-close="rangeModal" aria-label="关闭时间区间选择">
            <Ph name="x" />
          </button>
        </div>

        <div className="range-body">
          <div className="range-presets" id="rangePresets" role="group" aria-label="快捷区间" />

          <div className="range-calendar">
            <div className="range-calendar-head">
              <button id="rangePrevMonth" className="range-nav" type="button" aria-label="上一个月">
                <Ph name="caret-left" />
              </button>
              <div className="range-month-titles" id="rangeMonthTitles" aria-live="polite" />
              <button id="rangeNextMonth" className="range-nav" type="button" aria-label="下一个月">
                <Ph name="caret-right" />
              </button>
            </div>
            <div className="range-months" id="rangeMonths" />
          </div>
        </div>

        <div className="range-footer">
          <p className="range-summary" id="rangeSummary" aria-live="polite" />
          <div className="range-actions">
            <button id="rangeCancel" className="btn btn-quiet" type="button">
              取消
            </button>
            <button id="rangeApply" className="btn btn-primary" type="button">
              应用区间
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

function EvidenceDrawer() {
  return (
    <div id="evidenceDrawer" className="drawer-backdrop" hidden>
      <aside className="evidence-drawer" role="dialog" aria-modal="true" aria-labelledby="evidenceTitle" tabIndex={-1}>
        <div className="drawer-header">
          <div>
            <span id="evidenceStatus" className="evidence-status">交易证据</span>
            <h2 id="evidenceTitle">正在载入</h2>
            <p id="evidenceSubtitle">--</p>
          </div>
          <button className="modal-close" type="button" data-drawer-close aria-label="关闭交易证据">
            <Ph name="x" />
          </button>
        </div>
        <div id="evidenceContent" className="evidence-content" aria-live="polite">
          <div className="evidence-loading">正在读取本地证据…</div>
        </div>
      </aside>
    </div>
  );
}

function CategoryManagementModal() {
  return (
    <div id="categoryModal" className="modal-backdrop category-backdrop" hidden>
      <section className="modal-shell category-modal" role="dialog" aria-modal="true" aria-labelledby="categoryModalTitle" tabIndex={-1}>
        <header className="category-modal-header">
          <button className="category-mobile-back" type="button" data-category-back aria-label="返回分类列表">
            <Ph name="caret-left" />
          </button>
          <div className="category-modal-heading">
            <h2 id="categoryModalTitle">分类管理</h2>
            <p id="categoryModalMeta">正在读取分类目录</p>
          </div>
          <div className="category-modal-actions">
            <button id="newCategoryButton" className="btn btn-primary btn-sm" type="button">
              <Ph name="plus" />
              新建分类
            </button>
            <button className="modal-close" type="button" data-modal-close="categoryModal" aria-label="关闭分类管理">
              <Ph name="x" />
            </button>
          </div>
        </header>

        <div id="categoryDemoNotice" className="category-demo-notice" hidden>
          演示模式下可以查看分类目录，但不能新增、编辑、排序或停用。
        </div>

        <div className="category-workspace">
          <div className="category-list-pane" id="categoryListPane">
            <div className="category-search">
              <Ph name="magnifying-glass" />
              <input
                id="categorySearchInput"
                type="search"
                placeholder="搜索分类名称…"
                aria-label="搜索分类名称"
                autoComplete="off"
              />
            </div>
            <div id="categoryList" className="category-list" aria-label="分类列表" />
          </div>
          <div className="category-editor-pane" id="categoryEditorPane">
            <div id="categoryEditor" className="category-editor" aria-live="polite" />
          </div>
        </div>
      </section>
    </div>
  );
}

function CustomPromptModal() {
  return (
    <div id="promptModal" className="modal-backdrop prompt-backdrop" hidden>
      <section className="modal-shell prompt-modal" role="dialog" aria-modal="true" aria-labelledby="promptModalTitle" tabIndex={-1}>
        <header className="modal-header">
          <div className="prompt-modal-heading">
            <h2 id="promptModalTitle">我的常问</h2>
            <p id="promptModalMeta">正在读取</p>
          </div>
          <button className="modal-close" type="button" data-modal-close="promptModal" aria-label="关闭我的常问">
            <Ph name="x" />
          </button>
        </header>
        <div id="promptManager" className="prompt-manager" />
      </section>
    </div>
  );
}

function ProfileReportModal() {
  return (
    <div id="profileReportModal" className="modal-backdrop profile-report-backdrop" hidden>
      <section className="modal-shell profile-report-shell" role="dialog" aria-modal="true" aria-labelledby="profileReportTitle" tabIndex={-1}>
        <header className="profile-report-header">
          <div className="profile-report-brand">
            <BrandMark />
            <div>
              <h2 id="profileReportTitle">账单人格报告</h2>
              <p id="profileReportProgress">准备生成</p>
            </div>
          </div>
          <div className="profile-report-actions">
            <button id="refreshProfileReport" className="profile-report-refresh" type="button" hidden>
              <Ph name="arrows-clockwise" />
              重新生成
            </button>
            <button className="modal-close" type="button" data-modal-close="profileReportModal" aria-label="关闭账单人格报告">
              <Ph name="x" />
            </button>
          </div>
        </header>

        <div id="profileReportStale" className="profile-report-stale" hidden>
          <span>账本有了新变化，这里展示的是上次生成的画像。</span>
          <button id="updateProfileReport" type="button">更新画像</button>
        </div>

        <main id="profileReportViewport" className="profile-report-viewport" tabIndex={0} aria-live="polite">
          <div id="profileReportPages" className="profile-report-pages" />
        </main>

        <footer id="profileReportNavigation" className="profile-report-navigation" hidden>
          <button id="profileReportPrev" className="profile-report-nav-button" type="button" aria-label="上一页">
            <Ph name="caret-left" />
          </button>
          <div id="profileReportDots" className="profile-report-dots" role="tablist" aria-label="报告章节" />
          <button id="profileReportNext" className="profile-report-nav-button" type="button" aria-label="下一页">
            <Ph name="caret-right" />
          </button>
        </footer>
      </section>
    </div>
  );
}

export default function App() {
  return (
    <>
      <AppLoadingScreen />
      <OpeningOverlay />
      <div className="app-shell">
        <a className="skip-link" href="#main">
          跳到主要内容
        </a>
        <TopRail />
        <main className="main" id="main" tabIndex={-1}>
          <OverviewHero />
          <IntelligencePanel />
          <LedgerPanel />
          <SiteFooter />
        </main>
        <TrendModal />
        <CaptureModal />
        <BudgetModal />
        <AccountModal />
        <RangePickerModal />
        <CategoryManagementModal />
        <CustomPromptModal />
        <ProfileReportModal />
        <EvidenceDrawer />
        <div id="chatExpandBackdrop" className="chat-expand-backdrop" hidden aria-hidden="true" />
        <div className="toast-region" id="toastRegion" role="status" aria-live="polite" />
      </div>
    </>
  );
}
