# Jeanz CFO Brain · 项目介绍
> 一个本地优先的私人财务 Agent：用 iPhone 快捷指令捕获账单截图，用 Mac 本地 OCR 和规则解析生成结构化账本，再通过 Web 财务大脑和 DeepSeek 对话，把日常消费流水变成可追溯、可分析、可提问的个人现金流系统。
>

这份文档面向第一次接触本项目的人——如果你想了解它是什么、怎么搭起来、或者照着在自己机器上跑一套，从这里开始就够了。更偏规格细节的内容在同目录的 `README.md`。

---

## 1. 一分钟看懂
<img src="assets/cfo-architecture.svg" title="null" crop="0,0,1,1" id="aFWsm" class="ne-image"><img src="https://cdn.nlark.com/yuque/0/2026/png/22412697/1782388916874-95f6b5f8-57ee-42f1-a9ab-b0f364749b60.png" width="1200" title="" crop="0,0,1,1" id="ucc340db0" class="ne-image">

它做的事情其实只有一句话：**消费发生后，你几乎不用动手，账单就自己变成了能分析、能追问的数据。**

支付完成后，在 iPhone 上点一下快捷指令，账单截图就发到了邮箱。Mac 上的本地服务把邮件里的截图取下来，做 OCR、按规则解析出金额/时间/商户/分类，写进本地 SQLite 账本。然后打开网页，就能看到今日/本周/本月的支出、消费场景分布、现金流趋势，还能直接用中文问它「这个月最大的支出是什么」。

核心特点：

+ **本地优先**：账本、截图、OCR 文本都存在自己机器上，不依赖任何第三方记账平台。
+ **证据可追溯**：每一笔交易都保留原始 OCR 全文和截图路径，解析错了能回查、能改规则重跑。
+ **可对话**：接入 DeepSeek，但只把裁剪过的账本上下文喂给它，回答基于真实数据。

---

## 2. 为什么做它
传统记账工具的根本问题是「要人主动记」：打开 App、选分类、输金额、补备注。维护成本高，坚持不下来，数据也就不完整。

而且我们真正关心的，往往不是「今天花了多少」这一个数字，而是一些需要持续观察才能回答的问题：

+ 最近哪些消费场景变多了？
+ 外卖、咖啡、停车这些习惯有没有变化？
+ 某笔大额支出是不是挤占了日常预算？
+ 本月的预算节奏健康吗？
+ 能不能直接用一句话问账本，而不是自己翻流水？

所以这个项目不打算再做一个「需要你伺候」的记账软件，而是围绕四个主张设计：

1. **自动采集优先**——消费后只需触发一次快捷指令，剩下的交给机器。
2. **理解消费内容**——不只存金额，还识别商户、消费场景、支付方式。
3. **持续分析现金流**——按周期联动展示支出、场景权重、趋势和预算。
4. **随时自然语言对话**——把账本当成一个可以随口追问的对象。

---

## 3. 它能做什么
**消费数据采集。** iPhone 快捷指令对账单详情页截图，作为附件发到指定邮箱，邮件主题固定为 `CFO_CAPTURE_SCREENSHOT`。网页上点「消费数据同步」，Mac 端就通过 IMAP 扫描未读邮件、把命中的图片附件取下来。

**OCR 与账单解析。** 用 macOS 自带的 Vision OCR 识别截图（中文效果好且完全本地），再用规则从文本里解析出金额、支付时间、状态、商户、商品说明、支付方式、订单号等字段。OCR 原文单独留档，方便排查解析问题。

**分类与消费理解。** 按一组规则识别消费场景，例如外卖餐饮、咖啡奶茶、停车交通、超市便利、图书、演出票务、水电缴费、理财等。分类会影响后面的统计、筛选、趋势和对话上下文。

**Web 财务大脑。** 网页有四个区域：

+ **对话**——CFO Agent 对话区，支持快捷提问和自由输入。
+ **核心**——当前周期的总支出、笔数、最大单笔、置信度、消费场景权重和行为分析。
+ **账本**——交易流水，支持按分类筛选、分页查看。
+ **趋势**——弹窗里看日/周/月现金流折线图和预算使用情况。

**预算配置。** 右上角齿轮可以设日预算、周预算、月预算，保存在浏览器本地，并会参与趋势展示和对话上下文。

**DeepSeek 对话。** 提问时，服务端读本地账本、构造上下文后调用 DeepSeek，让回答基于真实账本而不是凭空编造。

**访问保护。** 配置访问口令后，打开页面需要登录；没配口令时直接禁止公网访问。

---

## 4. 一笔钱怎么变成可提问的数据<img src="assets/cfo-data-flow.svg" title="null" crop="0,0,1,1" id="ra2ca" class="ne-image"><img src="https://cdn.nlark.com/yuque/0/2026/png/22412697/1782388937304-981d3900-4159-464c-bf8c-469fe23ce8a0.png" width="1200" title="" crop="0,0,1,1" id="u9c63968d" class="ne-image">
跟着一笔交易走一遍，就理解了整个系统：

1. 你支付完成，打开微信或支付宝的账单详情页。
2. 在 iPhone 上触发快捷指令——它只做两件事：截图，然后把截图作为邮件附件发出去。
3. 在网页上点「消费数据同步」。
4. 服务端通过 IMAP 扫描未读邮件，主题匹配 `CFO_CAPTURE_SCREENSHOT` 的，把图片附件保存到 `data/mail_attachments/`。
5. 调用 Vision OCR 识别截图，OCR 文本存到 `data/ocr_texts/`。
6. 规则解析出各字段、识别分类、生成交易唯一 ID，写入 SQLite。
7. 网页读取快照数据，刷新统计和流水。
8. 你提问时，服务端把账本上下文传给 DeepSeek，返回自然语言分析。

这里有个关键设计：**第 6 步用「交易唯一 ID」做幂等写入**——同一笔交易重复同步也不会重复记账（详见 6.2）。

把同步入库和对话问答这两条链路按时间展开，各个组件之间的消息往来是这样的：<img src="assets/cfo-sequence.svg" title="null" crop="0,0,1,1" id="cn0xp" class="ne-image"><img src="https://cdn.nlark.com/yuque/0/2026/png/22412697/1782389050295-9c137698-d11d-480f-aa75-9bfbe027c9ea.png" width="1200" title="" crop="0,0,1,1" id="u6adfa3ae" class="ne-image">

---

## 5. 系统怎么搭的
整体分四层，职责清晰：

| 层 | 职责 | 主要组件 |
| --- | --- | --- |
| ① 移动端采集层 | 在账单页截图并发邮件 | iOS 快捷指令 |
| ② Mac 本地处理层 | 拉邮件、OCR、解析入库、编排 | `mail_sync.py` / `ocr_image.swift` / `bill_store.py` / `server.py` |
| ③ 数据与智能层 | 存证据与结构化交易、对话 | SQLite `cfo.sqlite` / `data.json` / DeepSeek |
| ④ 展示与访问层 | 网页分析与访问控制 | React + Vite UI / 口令认证 |


### 技术选型与理由
**采集用「快捷指令 + 邮件」**，而不是给手机写 App、开 HTTP 接口。原因是私人使用场景下，这套组合开发成本最低，也不用把任何服务暴露给手机端——截图借邮箱生态传递就够了。

**OCR 用 macOS Vision**，通过一段 Swift 脚本调用系统能力。本地、免费、对中文账单截图识别质量好，且不把截图传给外部服务。

**后端用 Python 标准库 HTTP Server + SQLite**。本地私有服务不需要重框架；SQLite 单文件、好备份、能直接用 SQL 查。

**解析用规则而不是直接喂大模型入库**。当前账单字段结构稳定，规则解析更可控、可解释、不烧 token；大模型只用在「对话分析」这一层。

**前端用 React + Vite**，趋势折线图由前端直接用 SVG 画，预算等轻状态存在浏览器本地。

**大模型用 DeepSeek API**，系统提示词独立成文件（`prompts/cfo_system_prompt.md`），方便单独维护 Agent 的回答边界和风格。

---

## 6. 关键设计细节
### 6.1 规则解析与分类
解析逻辑集中在 `bill_store.py`，把一段 OCR 文本变成结构化字段：识别金额、支付时间（支持中文日期和标准格式）、支付状态、商户、商品说明、支付方式、交易单号等，再根据一组 `CATEGORY_RULES` 命中消费场景。

每条解析结果还带一个**置信度**：从一个基础分起步，命中金额、状态、时间、商户、分类等字段就逐项加分。置信度低的交易，提醒你回去核对原始截图。

### 6.2 幂等去重
每笔交易都有一个 `transaction_uid`：优先用账单里的交易单号生成；没有单号时，对「来源 + 金额 + 时间 + 商品 + 支付方式」做哈希。写库时按这个 ID 做 upsert，所以**同一封邮件、同一张截图重复处理，也不会重复记账**。

### 6.3 数据模型
<img src="assets/cfo-data-model.svg" title="null" crop="0,0,1,1" id="BG3zh" class="ne-image"><img src="https://cdn.nlark.com/yuque/0/2026/png/22412697/1782389077715-34cc12fa-0f73-43b7-bd56-f43e9ace6afa.png" width="1200" title="" crop="0,0,1,1" id="uc29e08cb" class="ne-image">

设计上把**原始证据**和**结构化结果**分开存：

+ `transactions`——结构化交易主表，网页和对话主要读它。展示用的 `merchant`、`thing` 可以随时修正，但 `product`、`raw_text` 保留原始证据不建议覆盖。
+ `raw_bill_captures`——原始截图 / OCR 证据表，存 OCR 全文和截图路径。交易通过 `raw_capture_hash` 指回它，错了能回溯。
+ `raw_notifications` / `finance_events`——早期通知链路和事件抽象表，目前不是主链路，保留用于后续多源数据融合。

### 6.4 对话上下文注入
<img src="https://cdn.nlark.com/yuque/0/2026/png/22412697/1782389123272-e77a49d2-156a-4866-b309-e4b332b24300.png" width="1200" title="" crop="0,0,1,1" id="uddb79274" class="ne-image">

这是「回答基于真实账本」的关键。你提问时，服务端不会把整个数据库甩给大模型，而是构造一份裁剪过的上下文：

+ `selected_period_stats`——当前周期的笔数、总支出、分类汇总、最大单笔；
+ `month_stats`——本月汇总；
+ `recent_transactions`——最近若干笔交易（上限 40 笔）；
+ `user_budget_config`——你配置的日/周/月预算。

然后按顺序组装成消息：系统提示词 → 账本上下文 JSON → 最近对话历史 → 当前问题，发给 DeepSeek。模型被明确要求：只基于上下文回答，数据不足就直说样本不足，不编造账本里没有的交易。

### 6.5 前端数据联动
前端拿到交易列表后，周期筛选、汇总计算、分类权重、趋势折线、预算进度全部在浏览器里完成：今日/本周/本月/全部四个周期联动；趋势按日看近 7 天、按周看本月、按月看本年至今；预算存在浏览器本地，同时参与趋势和对话上下文。

---

## 7. 怎么跑起来
下面这套足够让你在自己的 Mac 上把它跑起来。

### 7.1 环境要求
+ macOS（OCR 依赖系统的 Vision，Swift 可用）
+ Python 3
+ Node.js / npm（或用项目内置的 Node）
+ 一个开了 IMAP 的邮箱及其授权码
+ 一个 DeepSeek API Key

### 7.2 配置 `.env`
在 `cfo_agent_poc/.env` 里填好下面的变量。**真实的 **`.env`** 不要提交或公开。**

```bash
# Web 访问
CFO_ACCESS_TOKEN=你的访问口令
CFO_WEB_HOST=127.0.0.1
CFO_WEB_PORT=8091

# 邮箱同步
CFO_MAIL_IMAP_HOST=imap.qq.com
CFO_MAIL_USER=你的邮箱
CFO_MAIL_PASSWORD=你的IMAP授权码
CFO_MAIL_MAILBOX=INBOX
CFO_MAIL_SUBJECT=CFO_CAPTURE_SCREENSHOT

# DeepSeek
DEEPSEEK_API_KEY=你的DeepSeek密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_THINKING=disabled
```

### 7.3 设置 iPhone 快捷指令
快捷指令只需要做两步：

1. 对当前账单详情页**截图**；
2. 把截图作为**邮件附件**发到上面配置的同步邮箱，主题填 `CFO_CAPTURE_SCREENSHOT`。

使用时：支付后打开微信/支付宝账单详情页 → 确认页面包含金额、时间、商品说明、支付方式 → 触发快捷指令 → 等邮件发出。

### 7.4 启动服务
在项目根目录执行：

```bash
./cfo_agent_poc/start_cfo_web.sh
```

脚本会自动读取 `.env`、必要时构建前端、然后启动服务，默认监听 `127.0.0.1:8091`。浏览器打开 `http://localhost:8091/`，输入访问口令进入。

### 7.5 日常使用
+ 点「消费数据同步」：拉最新邮件截图并写入账本。
+ 顶部切换周期：今日 / 本周 / 本月 / 全部。
+ 看「核心」：理解当前周期的主要支出和消费场景。
+ 看「账本」：按分类筛选具体交易。
+ 点「趋势」：看日/周/月现金流和预算使用率。
+ 点齿轮：维护日 / 周 / 月预算。
+ 在对话框提问：让 CFO Agent 基于本地账本回答，例如「我今天花了多少钱」「这个月最大的支出是什么」「预算使用率是多少」。

### 7.6 手动处理单张截图
不走邮箱也行，在 `cfo_agent_poc` 目录下直接处理一张图片：

```bash
cd cfo_agent_poc
python3 process_bill_image.py /path/to/bill.png --source manual --source-hint alipay
python3 web_app/generate_snapshot.py   # 重新生成静态快照
```

### 7.7 备份数据库
```bash
./cfo_agent_poc/backup_cfo_db.sh   # 备份写入 data/backups/
```

### 7.8 公网演示（可选）
项目提供 `start_public_demo.sh`，用 `cloudflared` 临时把本地服务暴露到公网。**公网访问前必须先配置 **`CFO_ACCESS_TOKEN`**。** 私人财务数据敏感，建议只临时演示，长期使用就留在本地或可信内网。

---

## 8. 安全与隐私
+ 账本、截图、OCR 文本默认都在本机，不依赖第三方记账平台，方便自查和删除。
+ DeepSeek 只在你发起对话时接收**裁剪过**的账本上下文，不会直接读数据库文件。
+ 访问页面需要 `CFO_ACCESS_TOKEN`，API 支持 Cookie / Bearer / 自定义 Header 三种认证。
+ 邮箱授权码和 DeepSeek Key 存在 `.env`，不要提交到公开仓库。

需要明确的是：当前对话链路仍会把部分交易上下文发给 DeepSeek。如果想完全本地化，后续需要换成本地 LLM。

---

## 9. 现状边界与后续方向
**当前的边界：**

+ 手机侧仍需手动触发快捷指令，不是完全后台无感采集。
+ 邮箱同步默认只扫未读邮件；若邮件被提前标为已读，可能不会被同步。
+ OCR 质量受截图清晰度和页面布局影响。
+ 分类是规则驱动，遇到新商户/新场景需要补规则。
+ 对话依赖外部 API 和网络。
+ 预算存在浏览器本地，换浏览器或清缓存后需重设。

**可以继续演进的方向：**

+ 在网页上直接编辑 `merchant` / `thing` / `category`。
+ 引入 LLM 辅助分类，但保留规则兜底和人工确认。
+ 每日 Morning Brief：自动生成昨日支出、预算进度、异常提醒。
+ 接更多采集源：银行短信、Apple Wallet、信用卡邮件账单。
+ 支持本地模型，减少隐私数据外发。
+ 数据导出：CSV、月度报告。
+ 更细的预算体系：餐饮预算、娱乐预算、大额专项预算。

---

## 10. 命令速查
```bash
# 启动 Web 服务
./cfo_agent_poc/start_cfo_web.sh

# 手动构建前端
export PATH="$PWD/cfo_agent_poc/bin/node/bin:$PATH"
npm --prefix cfo_agent_poc/web_app run build

# 手动处理一张账单截图（在 cfo_agent_poc 目录下）
python3 process_bill_image.py /path/to/bill.png --source manual --source-hint alipay

# 重新生成静态快照
python3 cfo_agent_poc/web_app/generate_snapshot.py

# 备份数据库
./cfo_agent_poc/backup_cfo_db.sh

# 健康检查
curl http://127.0.0.1:8091/health
```

---

## 11. 一句话总结
Jeanz CFO Brain 把「消费发生后的数据发现、结构化、归类、分析和问答」尽量自动化——你只在支付后点一下快捷指令，剩下的它来做，最终把日常流水变成一个能持续理解、随时追问的个人现金流系统。
