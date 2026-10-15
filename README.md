# 循动 · 大学生运动计划与训练记录平台

手机与桌面自适应的 FastAPI 应用，支持安装到手机桌面的 PWA。核心流程为：制定计划 → 记录运动 → 查看趋势 → 保存周复盘 → 调整计划。

## 快速启动（已有虚拟环境）

在 PowerShell 中执行：

```powershell
cd D:\sports_platform
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

浏览器打开 http://127.0.0.1:8000 。CMD 请先用 `cd /d D:\sports_platform` 切换目录。首次安装项目可参考后面的环境安装说明。

## 2.0 版本功能

- 首页、记录、计划、我的四个入口；手机底部导航，桌面侧栏。
- 原生 HTML/CSS 趋势图，无外部图表 CDN 依赖。
- 训练记录新增、编辑、删除和分页；计划创建、编辑、删除。
- 最近 7 天与前 7 天对比；完成率采用当前有效计划目标。
- 每个自然周一份可更新的复盘笔记，支持记录下周行动；旧周笔记保留在数据库，当前界面只显示本周。
- 按账号隔离的本地训练草稿，需手动恢复和提交；退出登录清除当前账号草稿。离线重新打开时显示公共离线页面，联网登录后可恢复草稿。
- JSON 导出所有训练记录；建议明确标注规则来源或模型来源。
- PWA manifest、192/512 图标、安装说明和 Service Worker。只缓存公共静态资源，不缓存接口、账号页面和训练数据。

### 手机安装

先部署到 HTTPS 地址，再在手机浏览器打开：

- Android Chrome：网页「安装到手机」，或浏览器菜单中的安装/添加到主屏幕。
- iPhone Safari：分享 → 添加到主屏幕。
- 不支持自动安装提示的浏览器会显示手动安装说明。

这是可安装网页应用，不是 APK 或应用商店安装包。普通局域网 HTTP 地址不满足 PWA 安装要求；localhost 只用于本机开发。安装要求参考 [MDN](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable)。

### 数据兼容与边界

升级启动时自动新增 `weekly_reflections` 表，保留现有用户、记录和计划；没有删除或重建现有表。沿用同日同项目唯一记录规则，需要合并时编辑原记录。周统计是滚动 7 天，复盘笔记按服务器日历周归档（周一开始）。生产环境应配置与目标用户一致的服务器时区。

本版适合小范围试用。找回密码、登录限流、数据库迁移管理、自动备份恢复及监控仍需在扩大使用前完善。暂无后台自动同步、健康平台对接和原生 App 上架能力。

### 验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_regressions.py -v
node tests/frontend.cjs
node --check app/static/app.js
```

真实浏览器测试（需要本机安装 Microsoft Edge）：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe tests/browser_smoke.py
```

浏览器测试自动在 8766 端口启动临时服务，使用临时数据库，不读写 `sports.db`。结束后关闭服务。截图生成到 `artifacts/`，已排除 Git 跟踪。

---

# 大学生运动计划与训练记录平台

一个适合课程作业演示的全栈 Web 项目，核心闭环：**每日记录 → 指标统计 → 阶段复盘 → AI训练建议**。

## 1. 已实现功能

- 用户注册 / 登录 / 退出
- 个人运动计划创建
- 每日运动训练记录：日期、项目、时长、距离、强度、热量、主观感受、备注
- 近 30 天指标统计
- 近 14 天运动时长折线图
- 7 天阶段复盘与目标完成度
- AI 训练建议：配置 API 后调用大模型；未配置时使用内置规则建议
- SQLite 本地运行 / PostgreSQL 云端部署
- Docker / Docker Compose

## 2. 本地运行

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload
```

浏览器打开 http://127.0.0.1:8000

## 3. Docker 本地运行

```bash
docker compose up -d --build
```

浏览器打开 http://127.0.0.1:8000

## 4. 部署到云服务器

推荐做法：租一台带公网 IP 的 Linux 云服务器（Ubuntu 22.04/24.04 均可），安装 Docker，然后：

```bash
git clone <你的 Git 仓库地址>
cd sports_platform
docker compose up -d --build
```

然后在云安全组 / 防火墙放行 TCP 8000 端口，通过：

`http://你的公网IP:8000`

即可访问。

正式答辩时可以进一步使用 Nginx + HTTPS 域名，把 8000 隐藏到反向代理后面。

## 5. 云端数据库

`docker-compose.yml` 已经包含 PostgreSQL。服务器重启后数据仍保存在 `pgdata` 卷里。

## 6. AI API（可选）

复制 `.env.example` 为 `.env`，填写：

```env
AI_API_BASE=https://api.openai.com/v1
AI_API_KEY=你的APIKey
AI_MODEL=gpt-4o-mini
```

然后：

```bash
docker compose up -d --build
```

不配置 AI API 也能运行完整作业，系统会使用本地规则生成训练建议。

## 7. 作业答辩可以这样讲

系统面向“缺少持续运动计划和过程反馈”的大学生用户，围绕运动计划、日常训练记录、数据统计和阶段复盘构成闭环，并用 AI 作为个性化训练建议模块。

技术架构：前端 HTML/CSS/JavaScript + 原生趋势图；后端 FastAPI；ORM 使用 SQLAlchemy；数据库本地 SQLite、云端 PostgreSQL；Docker 完成部署环境一致性。

## 8. 项目结构

```text
sports_platform/
├── app/
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── routers/
│   ├── services/
│   │   ├── analytics.py
│   │   └── ai_advice.py
│   ├── templates/index.html
│   └── static/
│       ├── app.js
│       └── style.css
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```


## 9. 本次完善与验证

- 登录改为数据库保存的随机会话（仅保存令牌哈希），有效期 7 天；退出会立即撤销会话。旧的 uid Cookie 不再作为登录凭据，更新后需重新登录。
- 阶段复盘使用今天有效的计划目标；多个有效计划取开始日期最新的一条，同日取最新创建的一条；没有有效计划时采用 150 分钟。统计窗口为近 7 天，完成率保留真实值，进度条最多显示 100%。
- 修复计划标题、目标、运动项目、感受及备注的 HTML 注入问题；使用浏览器本地日期预填表单；图表 CDN 不可用时仍加载计划与记录。
- 数据库自动新增 login_sessions 表，现有用户、计划及记录无需迁移或清空。
- Docker 构建排除本地数据库、虚拟环境、Git 和 .env，避免把本地数据打包进镜像。
- 云端 HTTPS 环境设置 COOKIE_SECURE=true；本地 HTTP 保持 false。Docker Compose 会传入该变量。多实例必须连接同一个 PostgreSQL 数据库。
- postgres:// 和 postgresql:// 连接串自动适配已安装的 psycopg 驱动。

运行回归测试（使用独立内存数据库，不修改 sports.db）：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_regressions.py" -v
node --check app/static/app.js
node tests/frontend.cjs
```

云端 PostgreSQL 驱动配置参考：[SQLAlchemy 官方文档](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html)。接口测试采用 [FastAPI TestClient](https://fastapi.tiangolo.com/tutorial/testing/)。

## 找运动搭子

新增「搭子」入口，支持：

- 每个账号发布一条当前运动状态：运动项目、具体日期和时间、公共运动地点、地图选点和补充说明；可更新或撤下。
- 已登录用户可在地图和列表中发现状态，按运动项目筛选、分页加载；到达约定时间后自动从公开结果隐藏。
- 点击状态「加为聊天搭子」直接建立双方私聊，同一对用户复用会话；支持消息持久化、历史消息和页面内每 4 秒刷新。当前不设好友申请审批，不提供后台推送。
- 运动状态公开给已登录用户；私聊仅限双方访问，个人训练记录仍保持账号隔离。
- 「定位到我附近」需浏览器定位授权（通常需 HTTPS 或 localhost），仅移动地图视野。发布位置来自用户主动点击的地图选点，不追踪实时位置。
- 地图交互使用本地打包的 Leaflet 1.9.4（许可证见 `app/static/vendor/leaflet/LICENSE`）；底图使用 OpenStreetMap 在线瓦片，需要网络可达。底图不可用时显示提示，状态列表和聊天仍可用。遵循 [OSM 瓦片使用政策](https://operations.osmfoundation.org/policies/tiles/)，上线扩大使用前应选定适合部署地区的地图服务。
- 数据库启动时仅新增 `buddy_statuses`、`buddy_chats`、`buddy_messages` 表，无需清空原有计划和记录。时间以 UTC 保存，前端按用户浏览器时区显示。

验证：`python -m unittest discover -s tests -p "test_*.py" -v`；`node tests/frontend.cjs`；`python tests/browser_smoke.py`。浏览器用两个独立账号验证地图发布、私聊往返、状态撤下和聊天记录保留，均使用临时数据库。
