# 循动 · 大学生运动搭子与运动管理平台

面向校园日常运动的手机优先 Web 应用：发现同校搭子 → 聊天确认运动 → 赴约与反馈 → 记录、计划和复盘。后端使用 FastAPI、SQLAlchemy，前端使用原生 HTML/CSS/JavaScript，支持 SQLite、PostgreSQL 和可安装 PWA。

## 4.0 功能与规则

### 手机界面与发现搭子

- 底部导航为首页、找搭子、记录、消息、我的；首页展示近期约定和运动进度，计划可从首页或我的进入。
- 森林绿、晴空蓝、轻盈紫、夜间、跟随系统五种外观，设置保存到账号。轻量动效尊重系统“减少动态效果”。
- 默认学校为湘潭大学，允许修改；学校信息由用户自行填写，不代表学籍认证。发现页默认同校，可切换全部学校。
- 列表优先、可切换地图；按运动关键字、场地、水平筛选，支持评分优先和时间最近排序。
- 日期筛选包含今天及之后四天，共五天；时段为上午 06:00–12:00、下午 12:00–18:00、晚上 18:00–24:00。日期与时段按浏览器时区解释；不限时段时仍可看到凌晨状态。
- 每人最多发布三条尚未开始的状态；填写项目、时间、场地、水平、时长、人数和说明。坐标可选，文字场地也能发布。

### 聊天、运动邀请与履约

- 私聊保留历史和未读数，支持向上加载历史、输入草稿和站内新消息提示；页面可见时轮询。
- 私聊可发送运动邀请，双方确认项目、时间、地点与时长；待确认邀请到开始时间后显示为过期。
- 三人及以上的活动创建多人约定，最多二十人，包含发起者；支持加入、退出和群聊。私聊约定为两人。
- 改期需当前参加者全部同意，确认前原约定继续有效；时间冲突会提示，用户可明确选择继续。
- 取消必须填写原因；距离开始至少两小时算正常提前取消，不足两小时标记临时取消，不自动扣评分。
- 约定结束后，各参加者分别确认参加；全部确认后才完成。单方确认保留待确认状态，不自动判定别人缺席。
- 只有共同完成约定并确认参加的用户才能互评；同一搭子一票，可修改。评分显示均分与人数，不代表平台核验过线下活动。
- 公开展示完成约定次数；取消原因和履约详情仅参与者可查看。
- 双向黑名单阻止继续私聊与新互动，隐藏彼此的发现状态；原有记录保留。已有群聊不自动解散。
- 可举报相关用户/活动；管理员可处理举报、下架状态、限制社交功能七天或恢复。处理结果可在“我的举报”查看。

### 消息与系统通知

- 支持站内通知和用户主动开启的 Web Push；用户也可关闭系统通知。退出登录撤销当前会话的服务端推送订阅。
- 约定开始前两小时、三十分钟生成提醒；服务端约每二十秒检查一次，短暂中断只在十分钟补发窗口内处理。
- 系统推送依赖浏览器支持、用户授权、有效登录会话、推送网络和持续运行的后端。不能保证精确到秒；服务休眠期间不能执行定时提醒。
- iPhone / iPad 需要支持 Web Push 的系统版本（iOS / iPadOS 16.4 起），先添加到主屏幕，再从主屏幕打开并主动开启通知。[WebKit 官方说明](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/)

### 运动管理

- 运动计划和训练记录的创建、修改、删除；记录包含项目、日期、时长、距离、强度、主观感受等。
- 近七天统计、趋势图、计划进度和每周复盘；同日同项目记录沿用合并规则。
- 可导出训练记录 JSON。草稿仅保存在当前浏览器，须联网后手动提交；草稿和记录导出均不替代完整数据库备份。
- 可选 AI 训练建议，未配置接口时使用内置规则建议。
- PWA 仅缓存公共静态资源与离线提示，不缓存账号页面和业务接口；离线时不能聊天或确认约定。

## 正确打开与本地运行

**不要双击 `app/templates/index.html`。它是服务端模板，用 `file://` 打开会缺少样式和服务端功能。**

已有虚拟环境时，在项目目录运行 `start-local.cmd`，或使用 PowerShell：

```powershell
cd D:\sports_platform
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

浏览器打开 <http://127.0.0.1:8000/>。手机的 localhost 指向手机自身，手机使用部署好的 HTTPS 地址。

首次安装：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Android 可使用浏览器的安装/添加到主屏幕；iPhone 使用 Safari 分享 → 添加到主屏幕。这是可安装网页应用，不是 APK。

## 数据库与部署

未设置 `DATABASE_URL` 时默认使用项目目录的 `sports.db`。云端长期使用必须确认数据库确实持久化，不能仅凭“网站能打开”判断数据安全。

- 启动时增量建表，保留现有用户、计划、记录、私聊；旧搭子状态迁入新的活动表。坐标可空迁移保留原数据。
- PostgreSQL 的 `postgres://`、`postgresql://` 连接串会自动转为已安装的 psycopg 驱动格式。
- 备份后再升级；改 `DATABASE_URL` 只会切换连接目标，**不会自动将 SQLite 数据复制到 PostgreSQL**。
- HTTPS 生产环境设置 `COOKIE_SECURE=true`；本地 HTTP 保持 false。推送密钥保存在数据库中，完整备份需包含相关表。
- Docker Compose 提供本地 PostgreSQL 与命名卷；公开部署前替换示例密码，并配置 HTTPS。不要执行删除数据卷的命令。

详见 [Render 部署、备份与通知检查](docs/operations.md)。包含 Environment 页面定位、现有数据保护、管理员配置和实机验收步骤。

## 管理员

首次 4.0 初始化仅在数据库中已经存在精确用户名 `test02` 时授权，并记录这次尝试。后来注册同名账号不会自动成为管理员。需要显式授权或撤销时，使用服务端命令行工具；不要向他人发送数据库连接串。

```powershell
# 在已配置目标 DATABASE_URL 的服务端/受控终端中运行
python scripts/admin_role.py status --username test02
python scripts/admin_role.py grant --username test02
python scripts/admin_role.py revoke --username test02
```

工具要求应用已完成 4.0 初始化；不会创建用户、运行迁移或修改相似用户名。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -v
node tests/frontend.cjs
node tests/campus_frontend.cjs
.\.venv\Scripts\python.exe tests/browser_smoke.py
```

后端测试使用独立测试数据库；浏览器测试使用临时 SQLite 与无界面 Microsoft Edge，需本机已安装 Edge，截图保存在 Git 忽略的 `artifacts/`。覆盖手机布局、账号隔离、筛选、私聊、约定与群聊、主题、举报拉黑、记录计划与地图失败回退。真机系统推送、手机键盘和 PostgreSQL 部署还需按运维文档单独验收。

## 地图与运行边界

Leaflet 1.9.4 随项目打包（许可证位于 `app/static/vendor/leaflet/LICENSE`）；地图底图使用 OpenStreetMap。浏览器直连失败时尝试本站备用瓦片通道，支持重试；两条通道都不可达时，列表、文字场地与聊天仍可使用。没有离线地图包或批量预下载；扩大使用前应按 [OSM 瓦片使用政策](https://operations.osmfoundation.org/policies/tiles/) 选择合适的地图服务。

当前适合校园小范围试用。找回密码、登录限流、学籍认证、自动化备份恢复、监控告警和更大规模的队列调度仍需补齐；不能把代码测试通过视为完成长期生产运营验收。
