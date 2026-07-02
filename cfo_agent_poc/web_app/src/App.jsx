import heroImage from "../assets/cfo-agent-hero.png";
import openingImage from "../assets/opening-cfo-illustration.webp";

export const CRITICAL_IMAGE_URLS = [openingImage];

function AppLoadingScreen() {
  return (
    <div className="app-loading-screen" aria-hidden="true">
      <div className="loading-spinner" />
    </div>
  );
}

function OpeningOverlay() {
  return (
    <div className="opening-overlay" aria-hidden="true">
      <div className="opening-frame">
        <div className="opening-content">
          <div className="opening-copy">
            <div className="opening-kicker">PRIVATE CASHFLOW INTELLIGENCE</div>
            <div className="opening-title">
              <span>Jeanz</span>
              <span>CFO</span>
            </div>
            <div className="opening-scan" />
            <div className="opening-meta">LOCAL LEDGER / LIVE ANALYSIS / CONTROLLED ACCESS</div>
          </div>
          <div className="opening-illustration-wrap">
            <img className="opening-illustration" src={openingImage} alt="" />
            <div className="opening-illustration-glow" />
          </div>
        </div>
      </div>
    </div>
  );
}

function TopNav() {
  return (
    <header className="command-rail" aria-label="Jeanz CFO">
      <div className="brand">
        <div className="brand-mark" aria-hidden="true">C</div>
        <div>
          <div className="brand-title-row">
            <div className="brand-title">Jeanz CFO Brain</div>
            <button id="openBudgetSettings" className="icon-button" type="button" aria-label="预算配置" title="预算配置">⚙</button>
          </div>
          <div className="brand-subtitle">Local finance intelligence</div>
        </div>
      </div>

      <div className="period-control" role="tablist" aria-label="周期">
        <button className="period-btn active" data-period="today" type="button">今日</button>
        <button className="period-btn" data-period="week" type="button">本周</button>
        <button className="period-btn" data-period="month" type="button">本月</button>
        <button className="period-btn" data-period="all" type="button">全部</button>
      </div>

      <nav className="nav-module" aria-label="主导航">
        <div className="nav-list">
          <a className="nav-item active" href="#chat" data-nav-section="chat" aria-current="true">对话</a>
          <a className="nav-item" href="#signals" data-nav-section="signals">核心</a>
          <a className="nav-item" href="#ledger" data-nav-section="ledger">账本</a>
          <button id="openTrendModal" className="nav-item nav-button" type="button">趋势</button>
        </div>
      </nav>
    </header>
  );
}

function ChatHero() {
  return (
    <section className="command-console agent-hero" id="chat" aria-label="对话 CFO 智能体">
      <div className="agent-hero-copy">
        <div className="agent-eyebrow">PRIVATE CFO AGENT</div>
        <h1>和你的私人 CFO Agent 对话</h1>
        <p id="headerSummary">正在读取账本快照。</p>

        <div id="chatMessages" className="chat-messages" aria-live="polite" />
        <div className="quick-prompts">
          <button data-prompt-key="spend" data-question="我今天花了多少钱？" type="button">今日支出</button>
          <button data-prompt-key="largest" data-question="今天最大的支出是什么？" type="button">最大支出</button>
          <button data-prompt-key="analysis" data-question="分析下我今天的消费情况" type="button">消费分析</button>
          <button data-prompt-key="takeout" data-question="我今天外卖点得多吗？" type="button">外卖频率</button>
          <button data-prompt-key="budget" data-question="今日预算使用率是多少？" type="button">预算状态</button>
        </div>
        <form id="chatForm" className="chat-form">
          <label htmlFor="chatInput">输入问题</label>
          <div className="chat-input-row">
            <input id="chatInput" type="text" autoComplete="off" placeholder="问问你的 CFO Agent" />
            <button type="submit">发送</button>
          </div>
        </form>
      </div>

      <div className="agent-visual" aria-hidden="true">
        <div className="agent-visual-label">LIVE LEDGER BRAIN</div>
        <div className="agent-portrait-frame">
          <img className="agent-portrait" src={heroImage} alt="" />
          <div className="agent-portrait-orbit agent-portrait-orbit-one" />
          <div className="agent-portrait-orbit agent-portrait-orbit-two" />
          <div className="agent-portrait-halo" />
          <div className="agent-portrait-shine" />
        </div>
        <div className="agent-visual-card agent-visual-card-bottom">
          <strong>Ask anything</strong>
          <span>今日支出 / 最大单笔 / 消费分析 / 预算状态</span>
        </div>
      </div>
    </section>
  );
}

function IntelligencePanel() {
  return (
    <section className="brain-grid">
      <section className="neural-panel intelligence-panel" id="signals" aria-label="财务智能核心">
        <div className="panel-heading">
          <div>
            <div className="panel-title-row">
              <h2>财务智能核心</h2>
              <button id="openSyncModal" className="sync-open-button" type="button">消费数据同步</button>
            </div>
            <p id="coreNarrative">等待 Agent 建立当前消费画像。</p>
          </div>
          <div className="panel-actions">
            <span className="live-chip" id="analysisState">Learning</span>
          </div>
        </div>

        <div className="neural-stage">
          <div className="core-metric">
            <span id="periodLabel">今日净支出</span>
            <strong id="coreAmount">--</strong>
            <small id="primaryMeta">--</small>
          </div>

          <div className="neural-map" aria-hidden="true">
            <div className="ring ring-one" />
            <div className="ring ring-two" />
            <div className="ring ring-three" />
            <div className="scan-plane" />
            <div className="core-pulse">
              <span>AI</span>
              <small>CFO</small>
            </div>
          </div>

          <div className="node-cloud" id="coreNodes" />
        </div>

        <div className="metric-matrix" aria-label="核心指标">
          <div><span>周期累计</span><strong id="monthSpend">--</strong></div>
          <div><span>消费笔数</span><strong id="budgetUsage">--</strong></div>
          <div><span>最大单笔</span><strong id="largestSpend">--</strong></div>
          <div><span>解析置信</span><strong id="confidenceScore">--</strong></div>
        </div>

        <div className="intelligence-synthesis">
          <div className="analysis-feed" aria-label="Agent 对消费行为的分析">
            <div className="mini-heading analysis-heading">
              <h3>Agent 对消费行为的分析</h3>
              <span id="signalMeta">等待样本</span>
            </div>
            <div id="decisionFeed" className="decision-feed" />
          </div>

          <div className="category-console">
            <div className="mini-heading">
              <h3>消费场景权重</h3>
              <span id="categoryCount">--</span>
            </div>
            <div id="categoryStack" className="category-stack" />
          </div>
        </div>
      </section>
    </section>
  );
}

function LedgerPanel() {
  return (
    <section className="ledger-panel" id="ledger" aria-label="交易事件流">
      <div className="ledger-heading">
        <div>
          <h2>交易流水</h2>
          <p>每一笔截图账单都会成为 Agent 可追溯的事实节点。</p>
        </div>
        <div id="filterBar" className="filter-bar" aria-label="分类筛选" />
      </div>
      <div id="transactionList" className="transaction-list" />
      <div id="ledgerPagination" className="ledger-pagination" aria-label="交易分页" />
    </section>
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
          <button className="modal-close" type="button" data-modal-close="trendModal" aria-label="关闭趋势弹窗">×</button>
        </div>

        <div className="trend-control" id="trendModeControl" role="tablist" aria-label="趋势周期">
          <button className="active" data-trend-mode="day" type="button">日</button>
          <button data-trend-mode="week" type="button">周</button>
          <button data-trend-mode="month" type="button">月</button>
        </div>

        <div className="trend-layout">
          <div className="trend-chart-panel">
            <div id="trendChart" className="trend-chart" aria-label="现金流折线图" />
            <div id="trendTooltip" className="trend-tooltip" hidden />
          </div>

          <aside className="trend-budget-panel" aria-label="预算状态">
            <div className="budget-summary">
              <div className="budget-kpi">
                <span id="trendBudgetLabel">月预算</span>
                <strong id="trendBudgetValue">--</strong>
              </div>
              <div className="budget-kpi budget-kpi-right">
                <span>使用率</span>
                <strong id="trendBudgetPercent">--</strong>
              </div>
            </div>
            <div className="budget-progress" aria-hidden="true">
              <span id="trendBudgetProgress" />
            </div>
            <div className="budget-rest">
              <span className="budget-rest-label">预计结余</span>
              <strong id="trendBudgetRemaining">--</strong>
              <div className="budget-rest-meta">
                <span id="trendBudgetAverageLabel">日均可用</span>
                <small id="trendBudgetAverage">--</small>
              </div>
            </div>
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
            <p id="syncSubtitle">主动连接邮箱，拉取最新账单截图并写入本地账本。</p>
          </div>
          <button className="modal-close" type="button" data-modal-close="syncModal" aria-label="关闭消费数据同步">×</button>
        </div>

        <div className="sync-body">
          <div className="sync-state-card" id="syncStateCard">
            <span id="syncStatusLabel">准备同步</span>
            <strong id="syncStatusTitle">等待开始</strong>
            <small id="syncStatusMeta">将扫描未读账单邮件，成功处理后自动标记已读。</small>
          </div>

          <div className="sync-metrics" aria-label="同步指标">
            <div><span>候选邮件</span><strong id="syncCandidateCount">--</strong></div>
            <div><span>命中邮件</span><strong id="syncMatchedCount">--</strong></div>
            <div><span>处理附件</span><strong id="syncAttachmentCount">--</strong></div>
            <div><span>新增交易</span><strong id="syncNewCount">--</strong></div>
          </div>

          <div className="sync-log-panel">
            <div className="mini-heading">
              <h3>同步明细</h3>
              <span id="syncFinishedAt">未开始</span>
            </div>
            <div id="syncItemList" className="sync-item-list">
              <div className="empty-state">点击下方按钮后开始同步。</div>
            </div>
          </div>

          <div className="sync-actions">
            <button id="startSyncButton" className="primary-action" type="button">开始同步</button>
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
            <p>维护日、周、月预算，用于趋势弹窗和 CFO Agent 对话上下文。</p>
          </div>
          <button className="modal-close" type="button" data-modal-close="budgetModal" aria-label="关闭预算配置">×</button>
        </div>

        <form id="budgetForm" className="budget-form">
          <label>
            <span>日预算</span>
            <input id="dayBudgetInput" type="number" min="0" step="1" inputMode="decimal" />
          </label>
          <label>
            <span>周预算</span>
            <input id="weekBudgetInput" type="number" min="0" step="1" inputMode="decimal" />
          </label>
          <label>
            <span>月预算</span>
            <input id="monthBudgetInput" type="number" min="0" step="1" inputMode="decimal" />
          </label>
          <div className="budget-actions">
            <button id="resetBudgetButton" className="secondary-action" type="button">恢复默认</button>
            <button className="primary-action" type="submit">保存配置</button>
          </div>
        </form>
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
        <TopNav />
        <main className="main">
          <ChatHero />
          <IntelligencePanel />
          <LedgerPanel />
        </main>
        <TrendModal />
        <SyncModal />
        <BudgetModal />
      </div>
    </>
  );
}
