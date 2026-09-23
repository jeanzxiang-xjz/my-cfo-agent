import openingImage from "../assets/opening-cfo-illustration.webp";

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

/**
 * 开场页：左侧品牌字幕、右侧线稿插画取景框。
 * 可点击 / Esc 跳过，一次会话只播一次，数据就绪或 1.2s 超时后收起。
 */
function OpeningOverlay() {
  return (
    <div className="opening-overlay" role="presentation">
      <div className="opening-frame">
        <span className="opening-rule opening-rule-top" aria-hidden="true" />
        <div className="opening-content">
          <div className="opening-copy">
            <p className="opening-kicker">PRIVATE CASHFLOW INTELLIGENCE</p>
            <div className="opening-title">
              <span>
                <i>Jeanz</i>
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
            <svg className="period-btn-icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
              <rect x="2.3" y="3.5" width="11.4" height="10.2" rx="2" />
              <path d="M2.3 6.7h11.4M5.7 2.3v2.4M10.3 2.3v2.4" />
            </svg>
            <span className="period-btn-label" id="customPeriodLabel">
              自定义
            </span>
          </button>
          <button id="periodClear" className="period-clear" type="button" aria-label="清除自定义区间，回到预设周期" hidden>
            <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
              <path d="M5 5l6 6M11 5l-6 6" />
            </svg>
          </button>
        </div>

        <div className="rail-actions">
          <button id="openTrendModal" className="rail-action" type="button" aria-label="现金流趋势" title="现金流趋势">
            <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
              <path d="M1.8 11.2 5.6 7l2.8 2.6L14.2 3.4" />
              <path d="M10.6 3.4h3.6v3.6" />
            </svg>
            <span className="rail-action-text">趋势</span>
          </button>
          <button id="openSyncModal" className="rail-action" type="button" aria-label="同步邮箱账单" title="同步邮箱账单">
            <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
              <path d="M13.6 6.9A5.7 5.7 0 0 0 3.2 5.1" />
              <path d="M2.4 9.1a5.7 5.7 0 0 0 10.4 1.8" />
              <path d="M13.9 2.6v3.9h-3.9M2.1 13.4V9.5H6" />
            </svg>
            <span className="rail-action-text">同步</span>
          </button>
          <button id="openBudgetSettings" className="rail-action rail-action-icon" type="button" aria-label="预算配置" title="预算配置">
            <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
              <path d="M3 4.2h10M3 8h10M3 11.8h10" />
              <circle cx="6.2" cy="4.2" r="1.7" className="is-filled" />
              <circle cx="10.4" cy="11.8" r="1.7" className="is-filled" />
            </svg>
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
                <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                  <path d="M6 3.5 10.5 8 6 12.5" />
                </svg>
              </span>
            </span>
            {/*
              走势徽标：抽象波形柱，不吃数据。高度包络是设计出来的——平缓起、
              中段主峰、尾部收在中位；刻意不做成向右上方的爬升，记账产品里那读作「花得更多」。
              每根柱是一条 non-scaling-stroke 的 line：容器横向被拉伸 3 倍多，
              用 stroke 才能保证柱宽和圆头在任何宽度下都不变形。
            */}
            <span className="hero-spark-chart" id="heroSparkChart" aria-hidden="true">
              <svg className="spark-wave-svg" viewBox="0 0 140 46" preserveAspectRatio="none" focusable="false">
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
                <line className="spark-wave-base" x1="0" y1="45.5" x2="140" y2="45.5" />
              </svg>
            </span>
          </span>

          <span id="heroProfileContent" className="hero-profile-content" hidden>
            <span className="hero-profile-mark" aria-hidden="true">
              <svg viewBox="0 0 48 48" focusable="false">
                <circle cx="24" cy="24" r="18" />
                <path d="M14 29.5c4.2-8.2 8.2-4.6 11.2-10.8 2.4-4.8 5.5-2.5 8.8-5.2" />
                <circle cx="14" cy="29.5" r="2.2" />
                <circle cx="25.2" cy="18.7" r="2.2" />
                <circle cx="34" cy="13.5" r="2.2" />
              </svg>
            </span>
            <span className="hero-profile-copy">
              <strong>你的钱，藏着一种生活流派</strong>
              <small id="heroProfileMeta">正在整理全部消费记录</small>
            </span>
            <span className="hero-profile-action">
              <span id="heroProfileActionLabel">生成画像</span>
              <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                <path d="M6 3.5 10.5 8 6 12.5" />
              </svg>
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
                <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                  <rect x="5.2" y="4.2" width="7.2" height="8.2" rx="1.2" />
                  <path d="M9.2 4.2V3.4A1.4 1.4 0 0 0 7.8 2H4.2A1.4 1.4 0 0 0 2.8 3.4v6.8a1.4 1.4 0 0 0 1.4 1.4h1" />
                </svg>
              </button>
              <button id="clearChatButton" className="chat-icon-action" type="button" aria-label="清空当前会话" title="清空会话">
                <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                  <path d="M2.6 4.8h10.8M5.3 4.8V3h5.4v1.8M4 4.8l.6 8.4h6.8l.6-8.4M6.6 7v4.2M9.4 7v4.2" />
                </svg>
              </button>
              <button id="expandChatButton" className="chat-mode-action" type="button" aria-label="展开对话" aria-expanded="false" aria-controls="heroChat" title="展开对话">
                <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                  <path d="M2.8 6V3.2H5.6M10.4 3.2h2.8V6M13.2 10v2.8h-2.8M5.6 12.8H2.8V10" />
                </svg>
                <span>展开对话</span>
              </button>
              <button id="closeChatExpandButton" className="chat-mode-action" type="button" aria-label="退出展开对话" title="退出展开对话" hidden>
                <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                  <path d="M5.6 2.8H2.8v2.8M10.4 2.8h2.8v2.8M13.2 10.4v2.8h-2.8M2.8 10.4v2.8h2.8" />
                </svg>
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
            <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
              <path d="M8 2.5v9M4.8 8.4 8 11.6l3.2-3.2M3 13.5h10" />
            </svg>
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
                <svg viewBox="0 0 12 12" aria-hidden="true" focusable="false">
                  <path d="M6 1.4 10.3 6 6 10.6 1.7 6Z" />
                </svg>
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
                <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                  <path d="M13.4 7.1A5.5 5.5 0 0 0 3.6 4.7" />
                  <path d="M2.6 8.9a5.5 5.5 0 0 0 9.8 2.4" />
                  <path d="M13.7 2.8v3.7h-3.7M2.3 13.2V9.5H6" />
                </svg>
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
                <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                  <path d="M8 2.4v11.2M2.4 8h11.2" />
                </svg>
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
                <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                  <path d="M2.6 8h9.6M8.4 4.2 12.2 8l-3.8 3.8" />
                </svg>
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
              <svg viewBox="0 0 32 32" focusable="false">
                <path d="M5.5 16s3.8-5.8 10.5-5.8S26.5 16 26.5 16 22.7 21.8 16 21.8 5.5 16 5.5 16Z" />
                <circle className="section-title-node" cx="16" cy="16" r="3.1" />
              </svg>
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
              <svg viewBox="0 0 32 32" focusable="false">
                <path d="M9 6.5h10l4 4v15l-2.6-1.9-2.4 1.9-2.4-1.9-2.4 1.9-2.4-1.9L9 25.5v-19Z" />
                <path d="M19 6.5v4h4M12.5 15h7M12.5 19h5" />
              </svg>
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
                  <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                    <path d="M4.5 6 8 2.5l3.5 3.5M4.5 10 8 13.5l3.5-3.5" />
                  </svg>
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
        <div className="modal-header">
          <div>
            <h2 id="trendTitle">现金流趋势</h2>
            <p id="trendSubtitle">正在读取现金流曲线。</p>
          </div>
          <button className="modal-close" type="button" data-modal-close="trendModal" aria-label="关闭趋势弹窗">
            <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
              <path d="M4.4 4.4 11.6 11.6M11.6 4.4 4.4 11.6" />
            </svg>
          </button>
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

        <div className="trend-layout">
          <div className="trend-chart-panel">
            <div id="trendChart" className="trend-chart" />
            <div id="trendTooltip" className="trend-tooltip" role="status" hidden />
            {/*
              跳转箭头是这块唯一「点了会离开弹窗」的控件，光靠一个图标说不清楚。
              在列表头一次性讲明白两个动作分别通向哪里，省得每张卡都重复一遍。
              整块 aria-hidden：同样的信息屏幕阅读器已经能从下面 ul 的 aria-label
              和每个按钮自己的 aria-label 里拿到，读两遍反而啰嗦。
            */}
            <div className="trend-breakdown-head" aria-hidden="true">
              <span className="micro-label">逐期明细</span>
              <span className="trend-breakdown-hint">
                点卡片高亮柱子 · 点
                <span className="trend-hint-chip">
                  <svg viewBox="0 0 16 16" focusable="false">
                    <path d="M6 3.5 10.5 8 6 12.5" />
                  </svg>
                </span>
                看当期交易
              </span>
            </div>
            <ul id="trendBreakdown" className="trend-breakdown" aria-label="逐期明细，点卡片高亮对应柱子，点箭头查看该期交易" />
          </div>

          <aside className="trend-budget-panel" id="trendBudgetPanel" aria-label="预算状态">
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
          </aside>
        </div>
      </section>
    </div>
  );
}

function SyncModal() {
  return (
    <div id="syncModal" className="modal-backdrop" hidden>
      <section className="modal-shell sync-modal" role="dialog" aria-modal="true" aria-labelledby="syncTitle">
        <div className="modal-header">
          <div>
            <h2 id="syncTitle">消费数据同步</h2>
            <p id="syncSubtitle">连接邮箱，拉取最新账单截图并写入本地账本。</p>
          </div>
          <button className="modal-close" type="button" data-modal-close="syncModal" aria-label="关闭消费数据同步">
            <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
              <path d="M4.4 4.4 11.6 11.6M11.6 4.4 4.4 11.6" />
            </svg>
          </button>
        </div>

        <div className="sync-body">
          <aside className="sync-guidance" aria-labelledby="syncGuidanceTitle">
            <span className="sync-guidance-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" focusable="false">
                <path d="M6.5 4.5h11v15h-11zM9 8h6M9 11.5h6M9 15h3.5" />
              </svg>
            </span>
            <div>
              <strong id="syncGuidanceTitle">同步时，请先打开账单详情页</strong>
              <p>确认金额、交易时间和商户完整显示后，再触发快捷指令。</p>
            </div>
          </aside>

          <div className="sync-state-card" id="syncStateCard">
            <span id="syncStatusLabel">准备同步</span>
            <strong id="syncStatusTitle">等待开始</strong>
            <small id="syncStatusMeta">将扫描未读账单邮件，成功处理后自动标记已读。</small>
          </div>

          <div className="sync-metrics" aria-label="同步指标">
            <div>
              <span className="micro-label">候选邮件</span>
              <strong id="syncCandidateCount">--</strong>
            </div>
            <div>
              <span className="micro-label">命中邮件</span>
              <strong id="syncMatchedCount">--</strong>
            </div>
            <div>
              <span className="micro-label">处理附件</span>
              <strong id="syncAttachmentCount">--</strong>
            </div>
            <div>
              <span className="micro-label">新增交易</span>
              <strong id="syncNewCount">--</strong>
            </div>
            <div>
              <span className="micro-label">待订正</span>
              <strong id="syncCorrectionCount">--</strong>
            </div>
          </div>

          <div className="sync-log-panel">
            <div className="mini-heading">
              <h3>同步明细</h3>
              <span id="syncFinishedAt">未开始</span>
            </div>
            <div id="syncItemList" className="sync-item-list" />
          </div>

          <div className="sync-actions">
            <button id="startSyncButton" className="btn btn-primary" type="button">
              开始同步
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
            <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
              <path d="M4.4 4.4 11.6 11.6M11.6 4.4 4.4 11.6" />
            </svg>
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
            <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
              <path d="M4.4 4.4 11.6 11.6M11.6 4.4 4.4 11.6" />
            </svg>
          </button>
        </div>

        <div className="range-body">
          <div className="range-presets" id="rangePresets" role="group" aria-label="快捷区间" />

          <div className="range-calendar">
            <div className="range-calendar-head">
              <button id="rangePrevMonth" className="range-nav" type="button" aria-label="上一个月">
                <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                  <path d="M10 3.2 5.2 8l4.8 4.8" />
                </svg>
              </button>
              <div className="range-month-titles" id="rangeMonthTitles" aria-live="polite" />
              <button id="rangeNextMonth" className="range-nav" type="button" aria-label="下一个月">
                <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                  <path d="M6 3.2 10.8 8 6 12.8" />
                </svg>
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
            <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
              <path d="M4.4 4.4 11.6 11.6M11.6 4.4 4.4 11.6" />
            </svg>
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
            <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M10.5 3.5 6 8l4.5 4.5" /></svg>
          </button>
          <div className="category-modal-heading">
            <h2 id="categoryModalTitle">分类管理</h2>
            <p id="categoryModalMeta">正在读取分类目录</p>
          </div>
          <div className="category-modal-actions">
            <button id="newCategoryButton" className="btn btn-primary btn-sm" type="button">
              <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M8 3v10M3 8h10" /></svg>
              新建分类
            </button>
            <button className="modal-close" type="button" data-modal-close="categoryModal" aria-label="关闭分类管理">
              <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                <path d="M4.4 4.4 11.6 11.6M11.6 4.4 4.4 11.6" />
              </svg>
            </button>
          </div>
        </header>

        <div id="categoryDemoNotice" className="category-demo-notice" hidden>
          演示模式下可以查看分类目录，但不能新增、编辑、排序或停用。
        </div>

        <div className="category-workspace">
          <div className="category-list-pane" id="categoryListPane">
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
            <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
              <path d="M4.4 4.4 11.6 11.6M11.6 4.4 4.4 11.6" />
            </svg>
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
              <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                <path d="M13.5 7.2A5.6 5.6 0 0 0 3.1 5.3" />
                <path d="M2.7 2.6v3.5h3.5" />
                <path d="M2.5 8.8a5.6 5.6 0 0 0 10.4 1.9" />
                <path d="M13.3 13.4V9.9H9.8" />
              </svg>
              重新生成
            </button>
            <button className="modal-close" type="button" data-modal-close="profileReportModal" aria-label="关闭账单人格报告">
              <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                <path d="M4.4 4.4 11.6 11.6M11.6 4.4 4.4 11.6" />
              </svg>
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
            <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M10 3.5 5.5 8 10 12.5" /></svg>
          </button>
          <div id="profileReportDots" className="profile-report-dots" role="tablist" aria-label="报告章节" />
          <button id="profileReportNext" className="profile-report-nav-button" type="button" aria-label="下一页">
            <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M6 3.5 10.5 8 6 12.5" /></svg>
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
        <SyncModal />
        <BudgetModal />
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
