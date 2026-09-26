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

技术架构：前端 HTML/CSS/JavaScript + Chart.js；后端 FastAPI；ORM 使用 SQLAlchemy；数据库本地 SQLite、云端 PostgreSQL；Docker 完成部署环境一致性。

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
