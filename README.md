<div align="center">

**中文** · [English](README.en.md)

<img src="cfo_agent_poc/web_app/assets/cfo-agent-hero.webp" alt="Jeanz CFO Brain" width="640">

# My CFO Brain

**支付后点一下，账单自动变成能分析、能追问的个人现金流系统。**

一个自托管（Self-hosted）、支持多用户的私人财务 CFO Agent：<br>
iPhone 快捷指令把账单截图直传服务端 → OCR 与规则解析 → 每人一个 SQLite 账本 → Web 财务大脑 + LLM 对话。<br>
一套应用、一个域名，注册即用；跑在自己的 Mac 上（OCR 全程离线），或者部署到服务器 7×24 常驻。

[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux-black?logo=apple)](#-快速上手)
[![Python](https://img.shields.io/badge/python-3.x-3776AB?logo=python&logoColor=white)](#-快速上手)
[![React](https://img.shields.io/badge/react-19-61DAFB?logo=react&logoColor=black)](cfo_agent_poc/web_app)
[![SQLite](https://img.shields.io/badge/storage-SQLite-003B57?logo=sqlite)](#-设计亮点)
[![LLM](https://img.shields.io/badge/LLM-DeepSeek-4D6BFE)](#-设计亮点)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

[为什么做它](#-为什么做它) · [工作原理](#-一笔钱的旅程) · [快速上手](#-快速上手) · [架构](#-系统架构) · [设计亮点](#-设计亮点) · [Roadmap](#%EF%B8%8F-roadmap)

<img src="cfo_agent_poc/docs/assets/demo.gif" alt="Demo：从现金流趋势下钻到某一周、跳转到对应账本、切到全部看消费分析，再直接向账本提问" width="820">

</div>

---

## 💡 为什么做它

传统记账工具的根本问题是——**要人主动记**。打开 App、选分类、输金额、补备注……维护成本太高，绝大多数人坚持不了三个月，数据一断，分析就无从谈起。

而我们真正关心的，往往也不是「今天花了多少」这一个数字，而是一些需要**持续观察**才能回答的问题：

> - 最近哪些消费场景变多了？
> - 外卖、咖啡、停车这些习惯有没有悄悄变化？
> - 那笔大额支出，是不是挤占了日常预算？
> - 这个月的预算节奏还健康吗？
> - 能不能直接用一句话问账本，而不是自己翻流水？

所以这个项目不打算再做一个「需要你伺候」的记账软件，而是把**消费发生之后的一切**——数据发现、结构化、归类、分析、问答——尽量自动化。你只在支付后点一下 iPhone 快捷指令，剩下的交给机器。

```
你唯一要做的事：支付 → 点一下快捷指令。
系统替你做的事：收截图 → OCR → 解析 → 分类 → 入库 → 分析 → 随时回答你的提问。
```

## ✨ 特性一览

| | 特性 | 说明 |
|---|---|---|
| 📸 | **近乎无感的采集** | 支付后点一下 iPhone 快捷指令，截图经 HTTPS 直传账本，几秒后弹通知告诉你记了多少；不用配邮箱 |
| 👥 | **多用户，一套部署** | 注册登录、邀请码、每人独立账本；一个进程、一个端口、一个域名服务所有人 |
| 🔍 | **可插拔 OCR** | macOS 上走系统 Vision，免费、离线、截图不出本机；部署到 Linux 时切换到阿里云 OCR |
| 🧾 | **混合智能解析** | 本地抽取金额、时间、商户和订单号；规则、商户记忆与 DeepSeek 共同补全消费分类 |
| 🧠 | **财务大脑 Web UI** | 今日/本周/本月/全部四周期联动：总支出、场景权重、现金流趋势、预算进度 |
| 💬 | **可对话的账本** | 接入 DeepSeek，直接问「这个月最大的支出是什么」，回答基于真实账本数据 |
| 🔗 | **证据可追溯** | 每笔交易保留原始截图路径与 OCR 全文，解析错了能回查、改规则重跑 |
| ♻️ | **幂等去重** | 基于交易单号/内容哈希生成唯一 ID，同一张截图传几次都只记一笔 |
| 🔐 | **数据归自己** | 每个账户一个独立的账本目录（SQLite + 截图），物理隔离；上传密钥只写不读，泄露也看不到账 |

## 🎬 一笔钱的旅程

跟着一笔交易走一遍，就理解了整个系统：

<div align="center">
<img src="cfo_agent_poc/docs/assets/cfo-data-flow.svg" alt="消费数据处理流程" width="820">
</div>

1. **支付完成**，打开微信/支付宝的账单详情页；
2. **触发快捷指令「记一笔」**——截图，并带着你的上传密钥 POST 到 `/api/v1/captures`；
3. 服务端按内容哈希把截图存进**你的账本目录**，登记一个识别任务（同一张图重复上传不会重复记账）；
4. **OCR** 识别截图（macOS 走系统 Vision，Linux 走阿里云），原文留档到 `data/ocr_texts/`；
5. **规则解析**出金额、时间、商户等事实字段，生成交易唯一 ID，**幂等写入 SQLite**；几秒内把结果回给手机，弹出「已记账 ¥32.50 · 美团外卖」；
6. 本地规则与商户记忆先完成分类，陌生消费由后台 DeepSeek 使用裁剪字段补全；
7. 网页刷新统计、流水、趋势与预算进度；
8. 你提问时，服务端把**裁剪过的账本上下文**注入给 DeepSeek，返回基于真实数据的分析。

## 🚀 快速上手

### ⚡ 30 秒试玩（Demo 模式，零配置）

不需要注册、不需要 API Key、不需要快捷指令——用一份内置的虚构账本先看看它长什么样：

```bash
git clone https://github.com/jeanzxiang-xjz/my-cfo-agent.git
cd my-cfo-agent
./cfo_agent_poc/start_cfo_web.sh --demo
```

打开 [http://localhost:8091](http://localhost:8091)：免登录直达财务大脑，128 笔虚构交易撑起完整界面，对话框可以直接提问（未配置 LLM Key 时由内置分析回答）。看完再决定要不要接入自己的真实账单。

### 环境要求（接入真实账单时才需要）

> 只想先看看？上面的 Demo 模式只需要 Python 3 + Node.js，API Key 都不用。

- **macOS**，或 **Linux 服务器**（见下方「部署到 Linux 服务器」）
- Python 3.10+
- Node.js / npm（用于构建前端）
- 一个 [DeepSeek API Key](https://platform.deepseek.com/)（对话和低置信度分类用）

### 1. 克隆并配置

```bash
git clone https://github.com/jeanzxiang-xjz/my-cfo-agent.git
cd my-cfo-agent
cp cfo_agent_poc/.env.example cfo_agent_poc/.env
```

编辑 `cfo_agent_poc/.env`：

```bash
CFO_WEB_HOST=127.0.0.1
CFO_WEB_PORT=8091

# 平台数据目录：账户库 platform.sqlite 和每个用户的账本 tenants/<id>/，留空则用 cfo_agent_poc/data
CFO_HOME=

# 对外访问地址（会作为快捷指令的上传地址显示给用户），本机使用可留空
CFO_PUBLIC_BASE_URL=

# DeepSeek
DEEPSEEK_API_KEY=你的DeepSeek密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
```

> ⚠️ 真实的 `.env` 已被 `.gitignore` 排除，请勿提交或公开。

### 2. 启动并注册

```bash
./cfo_agent_poc/start_cfo_web.sh
```

脚本会自动读取 `.env`、按需构建前端并启动服务。打开 [http://localhost:8091](http://localhost:8091)：

- **第一个注册的人自动成为管理员**，不需要邀请码；
- 之后的人注册需要邀请码：管理员在网页右上角「账户」里点「生成邀请码」，或者在服务器上执行 `python3 cfo_agent_poc/accounts.py invite`。

### 3. 连接 iPhone

1. 网页右上角点 **「记一笔」→「生成上传密钥」**，复制密钥；
2. 安装「记一笔」快捷指令：管理员配置了 `CFO_SHORTCUT_URL` 时弹窗里有一键安装按钮，安装时按提示粘贴密钥；否则按 [图文教程](cfo_agent_poc/docs/shortcut-setup.md) 自己搭，只有「截屏 → 获取 URL 内容 → 显示通知」三步。

**日常使用**：支付 → 打开账单详情页（确认能看到金额/时间/商品/支付方式）→ 触发快捷指令，看到「已记账」通知就完成了。建议把快捷指令设为「轻点背面」双击触发。

> 需要通过公网访问（手机不在同一局域网）时，请部署到服务器并配好 HTTPS 域名，见下方「部署到 Linux 服务器」。

### 日常使用

| 操作 | 效果 |
|---|---|
| iPhone 上点「记一笔」 | 截图直传入账，几秒后弹通知告诉你结果 |
| 网页「记一笔」 | 连接 iPhone（生成 / 停用上传密钥）、查看最近上传、从电脑批量上传截图 |
| 顶部切换周期 | 今日 / 本周 / 本月 / 全部联动刷新 |
| 「核心」区域 | 当前周期总支出、最大单笔、消费场景权重与行为分析 |
| 「账本」区域 | 交易流水，按分类筛选、分页查看 |
| 「趋势」弹窗 | 日/周/月现金流折线与预算使用率 |
| 齿轮按钮 | 配置日 / 周 / 月预算（跟着账户走，换设备不丢） |
| 「账户」按钮 | 改称呼、改密码、退出登录；管理员在这里生成邀请码 |
| 对话框 | 「我今天花了多少钱？」「最近外卖是不是点多了？」 |

<details>
<summary><b>更多命令（账户管理 / 迁移旧实例 / 手动处理截图 / 备份）</b></summary>

```bash
# 账户管理
python3 cfo_agent_poc/accounts.py invite                # 生成一个邀请码（14 天有效、一次性）
python3 cfo_agent_poc/accounts.py users                 # 列出所有账户
python3 cfo_agent_poc/accounts.py reset-password 邮箱    # 生成新密码，并让该用户所有设备重新登录

# 把以前的单用户实例并入（只读旧目录，账单一行不改，迁移后核对交易数和金额）
python3 cfo_agent_poc/migrate_instance.py --src /path/to/old/cfo_agent_poc --email 用户邮箱

# 不走快捷指令，手动处理一张账单截图到某个账本
cd cfo_agent_poc
python3 process_bill_image.py /path/to/bill.png --source manual --ledger-dir data/tenants/<用户ID>

# 备份平台库和所有账本（写入 <CFO_HOME>/backups/）
./cfo_agent_poc/backup_cfo_db.sh

# 健康检查
curl http://127.0.0.1:8091/health
```

</details>

<details>
<summary><b>部署到 Linux 服务器（HTTPS 域名 + 阿里云 OCR）</b></summary>

macOS 之外没有 Apple Vision，OCR 需要换后端。`CFO_OCR_PROVIDER` 默认 `auto`：
macOS 走 Vision，其它系统走阿里云通用文字识别，也可显式指定 `vision` / `aliyun`。

```bash
# 只有走阿里云时才需要装依赖，项目其余部分仍是纯标准库
python3 -m venv .venv && . .venv/bin/activate
pip install -r cfo_agent_poc/requirements.txt
```

在 `cfo_agent_poc/.env` 里补上（用**仅授予 OCR 权限的 RAM 子用户**，别用主账号 AccessKey）：

```
CFO_OCR_PROVIDER=aliyun
ALIBABA_CLOUD_ACCESS_KEY_ID=...
ALIBABA_CLOUD_ACCESS_KEY_SECRET=...
CFO_OCR_REGION=cn-hangzhou
CFO_PUBLIC_BASE_URL=https://cfo.example.com
```

应用只监听 `127.0.0.1:8091`，由反向代理统一对外提供 HTTPS 域名。`cfo_agent_poc/deploy/` 里有现成的配置：

| 文件 | 用途 |
|---|---|
| `Caddyfile` | 推荐。Caddy 自动申请和续期证书，几行就够 |
| `nginx.conf.example` | 已有 Nginx 时用；**必须转发 `Host` 头**，否则网页上的保存、上传会被当成跨站请求拒掉 |
| `cfo-web.service` | systemd 服务，开机自启、挂了自动拉起 |

阿里云 OCR 不支持 HEIC/HEIF；iPhone 截屏本身是 PNG，正常不会遇到。

> 前端产物 `dist/` 不在版本库里，建议在开发机 `npm run build` 后上传，
> 服务器就不必安装 Node 工具链。

</details>

## 🏗️ 系统架构

<div align="center">
<img src="cfo_agent_poc/docs/assets/cfo-architecture.svg" alt="系统架构" width="820">
</div>

| 层 | 职责 | 主要组件 |
|---|---|---|
| ① 移动端采集层 | 在账单页截图，HTTPS 直传 | iOS 快捷指令「记一笔」 |
| ② 接入层 | 统一域名、HTTPS、上传体积限制 | Caddy / Nginx 反向代理 |
| ③ 服务端处理层 | 账户与会话、按用户绑定账本、截图队列、OCR、解析入库 | `accounts.py` · `tenancy.py` · `capture_queue.py` · `ocr_providers.py` · `bill_store.py` · `server.py` |
| ④ 数据与智能层 | 账户库、每人一个账本（证据 + 结构化交易）、LLM 对话 | `platform.sqlite` · `tenants/<id>/data/cfo.sqlite` · DeepSeek |
| ⑤ 展示层 | 财务大脑页面、账户与连接 iPhone | React 19 + Vite |

**几个刻意的技术取舍：**

- **采集用「快捷指令 + HTTPS 直传」而不是写手机 App 或走邮件**——快捷指令零安装成本；直传比「发邮件 → 服务端拉 IMAP」少了邮箱配置这一整步，结果还能当场弹回手机。手机上只放一把**只写不读**的上传密钥，丢了也看不到账。
- **数据隔离用「一人一库」而不是一张大表加 `user_id`**——每个用户一个账本目录，布局和单机版完全一样：现有 SQL 一行不用改，隔离是物理层面的，导出、注销、备份、迁移都只是操作一个目录。
- **OCR 做成可插拔而不是绑死一家**（`ocr_providers.py`）——macOS 上默认用系统 Vision：本地、免费、中文账单识别质量好，截图不出本机；但 Vision 是 Apple 独有的，要 7×24 常驻就得上 Linux 服务器，那里换成阿里云 OCR。对外只暴露 `ocr_image(path) -> str` 一个函数，下游解析器对换了哪家毫不知情。
- **入库用规则解析而不是让 LLM 直接写库**——账单字段结构稳定，规则更可控、可解释、零 token 成本；大模型只负责「对话分析」这一层。
- **后端用 Python 标准库 + SQLite**——不需要重框架；每个账本一个文件，好备份、可直接用 SQL 查询。请求进来先认证，再把「当前账本」绑定到这次请求上，没绑定就直接报错，不会回退到某个默认库。

## 🧩 设计亮点

### 原始证据与结构化结果分离

<div align="center">
<img src="cfo_agent_poc/docs/assets/cfo-data-model.svg" alt="数据模型" width="720">
</div>

`transactions` 存结构化交易（页面和对话读它），`raw_bill_captures` 存原始截图与 OCR 全文。交易通过 `raw_capture_hash` 指回证据表——**解析错了永远能回溯到原始截图**，改完规则可以重跑，展示字段（`merchant`/`thing`）随时可修正而不破坏证据。

### 幂等去重

每笔交易生成一个 `transaction_uid`：优先取账单里的交易单号；没有单号时对「来源 + 金额 + 时间 + 商品 + 支付方式」做哈希。写库按此 ID upsert——**同一张截图重复上传，或者同一笔账从不同截图再记一次，都不会重复记账**。

### 置信度打分

事实解析和消费分类分别记录置信度。金额、时间、状态、商户等事实只由 OCR 与规则解析器确定，大模型碰不到；分类则标记来自本地规则、商户记忆、人工覆盖还是 DeepSeek，避免错误分类反过来抬高解析置信度。

### 裁剪式上下文注入

<div align="center">
<img src="cfo_agent_poc/docs/assets/cfo-chat-context.svg" alt="对话上下文注入" width="720">
</div>

提问时服务端不会把整个数据库甩给大模型，而是构造一份裁剪过的上下文：当前周期统计、本月汇总、最近交易（上限 40 笔）、你的预算配置。系统提示词明确要求：**只基于上下文回答，数据不足就直说，不编造账本里不存在的交易。**

## 🔐 安全与隐私

- **每个账户的账本单独存放、彼此不可见**：账本、截图、OCR 文本都在 `tenants/<用户ID>/` 下，请求只能读到当前登录用户的目录，其他目录的截图一律打不开。
- **账户**：密码用加盐 scrypt 哈希保存；登录 cookie 是随机串，库里只存它的哈希；连续输错会被限流；写操作会校验请求来源，拒绝跨站请求。
- **上传密钥只写不读**：快捷指令里的密钥只能往账本里传截图，拿它访问任何读接口都按未登录处理；可以在网页上随时停用或换新，库里同样只存哈希。
- DeepSeek 对话只接收**裁剪过的**账本上下文；后台分类只发送商户、商品、平台和支付应用，不发送截图、OCR 全文、金额、银行卡或交易号。
- `.env`（API Key）与 `data/`（账户库、账本、截图、OCR 文本）均已在 `.gitignore` 中排除。

> 已知边界：
> - 对话链路会把部分交易上下文发给 DeepSeek。若需要完全本地化，可将 LLM 替换为本地模型（见 Roadmap）。
> - **`CFO_OCR_PROVIDER=aliyun` 时，账单截图会上传给阿里云 OCR**——这是在 Linux 上换取 7×24 常驻的代价。留在 macOS 用 Vision，截图就始终不出本机。
> - 部署到公网服务器时，所有用户的账本和平台的 API Key 都在那台机器上，运维者能看到全部数据。请务必走 HTTPS，并保管好服务器访问权限。

## 🗺️ Roadmap

- [x] 多用户：注册登录、邀请码、每人独立账本、快捷指令 HTTPS 直传
- [ ] 每个用户的用量配额（上传、OCR、对话 token）与开放注册
- [ ] 网页上直接编辑 `merchant` / `thing` / `category`
- [x] LLM 辅助分类（本地规则和商户记忆优先，低置信度后台补全）
- [ ] 每日 Morning Brief：昨日支出、预算进度、异常消费提醒
- [ ] 更多采集源：银行短信、Apple Wallet、信用卡邮件账单
- [ ] 本地 LLM 支持，实现完全离线
- [ ] 数据导出：CSV / 月度 Markdown 报告
- [ ] 分场景预算：餐饮、娱乐、大额专项

## 📚 更多文档

- [CFO Agent 系统提示词](cfo_agent_poc/prompts/cfo_system_prompt.md)
- [iPhone 快捷指令搭建指南](cfo_agent_poc/docs/shortcut-setup.md)

## 🤝 贡献

这是一个从真实个人需求长出来的项目。Issue、PR、想法讨论都欢迎——尤其是新的账单解析规则、新的采集源接入和本地 LLM 方案。

## 📄 License

[MIT](LICENSE)

---

<div align="center">

**如果这个项目给了你启发，欢迎点一个 ⭐️**

*让账本自己说话，而不是让你伺候账本。*

</div>
