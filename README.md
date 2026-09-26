# 2026-09-26 图片接口扩展

模型设置可切换 `gpt-image-2.0-4k`、`gpt-image-2`、`gpt-image-2.5-sunburst`，新安装默认 Sunburst。订单新增纯文生图、独立透明遮罩重绘、自定义比例/像素尺寸、同步/异步及 URL/Base64 返回；原有图片编辑与继续修改保留。使用入口、兼容边界和验证见 [图片接口适配](docs/sunburst-integration.md)。

最新便携包：[AIFACE 刷新修复版](dist/AIFACE-0.1.0-Windows-x64-Portable-RefreshFix-20260926-223955.zip)，约 182 MiB，包含上述图片接口扩展。已修复生成结果被任务详情阻塞、交付状态读取不一致导致自动刷新延迟的问题；网络查询异常时显示原因和下次查询时间。后端 277 项、前端 83 项测试及最终 ZIP 中文路径隔离 EXE 验收通过，详情见 [刷新问题修复](docs/refresh-delay-review.md) 和 [便携版说明](docs/portable-build.md)。

升级时退出旧程序，将新 ZIP 完整解压到新目录，再把旧目录的 `storage`、`.env`、`codex-settings.json`（存在时）复制到新目录中的 `AIFACE` 文件夹，之后运行其中的 `AIFACE.exe`。保留旧目录作备份，不要只替换 EXE。复制旧 `.env` 会保留原模型选择和 API 配置。

# 当前版本说明（2026-09-21）

2026-09-26 区域识别升级为 Codex 动态对象拆解 + MobileSAM 本地轮廓：支持区分不同人物和物件、细节点选、放大、父级切换与选区修正。网页可直接调用已登录的 Codex CLI，也可导入外部子进程 JSON；使用与验收见 [Codex 元素拆解](docs/codex-elements.md)。源码版首次需安装本地分割模型，新版便携包已内置模型；自动分析需要目标电脑安装并登录 Codex CLI。

2026-09-26 已生成含 Codex 元素识别及路径配置的 Windows x64 便携版：分发 `dist/AIFACE-0.1.0-Windows-x64-Portable-Codex-20260926-214825.zip`，约 182 MiB，完整解压后双击 `AIFACE/AIFACE.exe`，无需安装 Python 或 Node.js。首次输入卡密，并在模型设置填写自己的 API Key。Codex 会自动检测，也可在模型设置中浏览选择程序路径。保留启动窗口，退出时按 Ctrl+C；详细构建与隔离验收记录见 [便携版说明](docs/portable-build.md)。旧 ZIP 保留。

2026-09-26 接入软件卡密授权：启动后网页先显示激活入口，授权成功进入原工作台；业务 API 与生成 Worker 同时受保护，运行中自动周期验证。授权配置位于 `project.yaml`，产品 ID 为用户提供的 `xhstupian`。卡密与模型 API Key 分别配置。接入与验证见 [公共组件说明](docs/commenlib-integration.md)。下方启动脚本用于开发环境；后端启动为无热重载模式。

2026-09-26 新增区域提示词编辑：主照片加载后在本地识别头发、五官、服饰等候选区域，点击区域填写修改要求、选择参考素材，再统一组装提示词。支持手动补充区域和组合预览。识别用于提示词定位，不做像素级图层编辑。详见 [功能与安装说明](docs/region-prompts.md)。

已切换为统一底图创作：主照片决定基础画面，素材通过提示词指定用途，风格控制表现。首次及继续修改共用左侧配置，每次生成一张。素材图可按编号继续添加；输出提供 11 种标准比例和 PNG、JPEG、WebP 三种格式，模型质量默认 high，可在模型设置中调整。

新数据默认写入 `storage/unified`，业务库 `storage/unified/database/aiface.sqlite3`，旧库与图片保留但不加载。运行中的旧服务请正常退出，再双击 `start-aiface.cmd` 或运行 `scripts/start-dev.ps1`；启动会自动迁移新库。不要将新存储路径配置回旧业务库。

当前协议见 [API](docs/api.md)、[架构](docs/architecture.md)、[数据模型](docs/data-model.md)；验证见 [统一流程验收](docs/unified-validation.md)。下方旧阶段记录中的固定风格/角色/比例规则已被上述文档取代。

---

# AIFACE 头像工作台

商家内部使用的头像接单工作台。首次生成 1 张直接交付，每次修改 1 张；修改轮次仅记录，不设置系统硬上限。

当前已实现阶段 5：首次生成一张交付图，修改成功自动替换，失败保留原图；历史版本可切回，下载当前单张原图，再独立确认完成或关闭订单。旧双图订单保留历史，须手动指定其中一个版本交付。真实人物/风格及修改效果仍待阶段 6；本次未新增真实供应商调用。首页插画为 CSS 示意图。

## 本地启动

### Cloudflare Tunnel 远程访问

域名为 <https://aiface.ai136.top>，已由 Cloudflare Access 应用 `aiface` 保护，允许使用已配置的邮箱一次性验证码登录。入口指向本机生产构建的前端 `127.0.0.1:3001`；Next.js 再将同源 `/api` 转发到 `127.0.0.1:8000`。不需要开放本机入站端口。浏览器若已有同一 Cloudflare Access 组织的有效会话，可能直接进入；无会话的请求应跳转到 Access 登录。

先按下方本地启动步骤运行后端和 Worker（`start-dev.ps1` 同时启动开发前端 `3000`，但 Tunnel 不再使用该端口）。另开 PowerShell，从项目根目录构建并启动独立的生产前端；两个命令使用同一终端，运行期间保留窗口：

```powershell
$env:AIFACE_NEXT_DIST_DIR = '.next-mobile'
npm.cmd --prefix frontend run build
Push-Location frontend
try { npm.cmd run start -- --port 3001 } finally { Pop-Location }
```

确认 <http://127.0.0.1:3001/api/health> 返回 `{"status":"ok"}` 后，再在另一终端启动专用 Tunnel：

```powershell
& 'C:\Users\Administrator\AppData\Local\Programs\cloudflared\cloudflared.exe' --protocol http2 --config 'E:\2-AI\AIFACE\scripts\cloudflared-aiface.yml' tunnel run
```

Tunnel 配置见 [cloudflared-aiface.yml](scripts/cloudflared-aiface.yml)。凭据 JSON 仅保存在本机 `.cloudflared` 目录，不提交到项目。现有 `crypto-trend-dashboard` 使用另一条 Tunnel 和 `trend.ai136.net`，两个进程可并行；不要用旧项目的默认配置启动 AIFACE。此处是手动启动的后端/Worker、生产前端和 Tunnel，尚未设置开机自启；电脑重启后三者都需重新启动。前端代码更新后，应先正常停止 `3001` 进程，再重建同一 `.next-mobile` 目录并启动，避免运行中覆盖构建文件。首次外网验收需由授权邮箱本人完成验证码登录，再检查页面及 `/api/health`。

若日后要重新创建该域名的 DNS 路由，须明确指定 `cert-ai136-top.pem` 并只传短主机名 `aiface`，避免默认的 `ai136.net` 授权证书将全名拼接到旧域名下；当前 DNS 已配置，无需重复运行：

```powershell
& 'C:\Users\Administrator\AppData\Local\Programs\cloudflared\cloudflared.exe' --origincert 'C:\Users\Administrator\.cloudflared\cert-ai136-top.pem' --config 'E:\2-AI\AIFACE\scripts\cloudflared-aiface.yml' tunnel route dns 51ef2c44-2013-4609-9f37-8e33c7515e57 aiface
```

双击项目根目录的 [start-aiface.cmd](start-aiface.cmd) 即可启动前端、后端和生成 Worker；启动成功后打开 <http://127.0.0.1:3000>。运行期间保留启动窗口，按 Ctrl+C 停止服务。启动失败时窗口会保留错误提示，不会一闪而过。此入口自动清除前端隔离验收环境变量，调用下方同一个启动脚本，不需要先激活虚拟环境。

环境：Windows PowerShell、Python 3.12.14（根目录 `.venv`）、Node.js 22.23.2、npm 10.9.8。所有命令在项目根目录执行；当前环境已安装依赖。

```powershell
.\scripts\start-dev.ps1
```

浏览器打开 <http://127.0.0.1:3000>。后端文档位于 <http://127.0.0.1:8000/api/docs>。脚本先升级数据库，再启动前后端和独立生成 Worker。按 Ctrl+C 停止本次启动的进程树；端口冲突不会停止已有服务。SmokeTest 模式只启动前后端，不处理付费任务。

运行日志保存在 `storage/logs/`，每次启动独立命名。无需激活环境，脚本会使用项目 Python 并为子进程设置环境路径。

首次安装或恢复依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e ./backend
npm.cmd --prefix frontend ci
```

pip 会在隔离构建环境中安装 setuptools，不向全局 Python 安装依赖。`.venv` 不可复制到另一台机器直接使用，应先使用 Python 3.12 创建本机虚拟环境。

## 配置与数据

现有 `.env` 保持原样。新环境可参考 `.env.example` 手动创建 `.env`，不要覆盖已有密钥。

| 变量 | 说明 |
| --- | --- |
| `image_api` | 可选模型密钥；基础工程不需要此值，也不调用供应商。后续模型调用前通过 `require_image_api()` 校验 |
| `image_api_url` | 当前 Apii 协议的 HTTPS 接口根地址，默认 `https://ai.apii.cn` |
| `image_model` | 图片模型名称，默认 `gpt-image-2.5-sunburst`，可切换 `gpt-image-2.0-4k` 或 `gpt-image-2` |
| `image_quality` | 图片质量：`auto`、`low`、`medium` 或 `high`，默认 `high` |
| `AIFACE_DATABASE_PATH` | SQLite 路径，默认 `storage/unified/database/aiface.sqlite3`；相对路径始终以项目根目录为基准 |
| `AIFACE_STORAGE_PATH` | 素材根目录，默认 `storage`；隔离测试时与数据库路径一起设置 |

前端不读取根目录 `.env`，通过 Next.js 将同源 `/api` 转发到 `127.0.0.1:8000`。数据库使用外键、WAL 和 5 秒锁等待；不在 API 启动时自动建表。当前迁移 head 为 `0010_order_lifecycle`；上传支持 JPEG、PNG、WebP 静态单帧，单张最多 20 MiB、4000 万像素。订单提交生成后由独立 Worker 后台处理，列表自动刷新“生成中／修改中／待交付”等状态，失败记录在订单详情中可恢复或重试。

页面入口：`/orders` 订单列表、`/orders/new` 新建、`/model-settings` 模型设置。左侧新建订单与其他导航项使用相同样式。模型设置只支持当前 Apii 图片编辑与任务查询协议；保存会更新根目录 `.env`，API Key 留空保持原值，页面不会回显密钥。运行中任务继续使用其模型、质量和接口地址快照；更换 API Key 前应等运行中任务完成。详情中上传主图片和按编号增加素材图，选择风格、尺寸、格式并填写完整提示词。主图片至多一张；移出素材保留历史文件，失效引用须修正。未保存的参数可撤销。保存配置不会调用模型或产生费用。

隔离验收前端可在启动进程中设置 `AIFACE_BACKEND_ORIGIN` 和 `AIFACE_NEXT_DIST_DIR`，默认分别为 `http://127.0.0.1:8000`、`.next`；自定义构建目录使用 frontend 下的 `.next-*`，不能指向项目外。本次隔离测试数据保留于 `storage/qa-stage2-20260920`，与默认业务数据分开。

单独运行后端或迁移：

```powershell
.\.venv\Scripts\python.exe -m alembic -c backend/alembic.ini upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
# 已有前后端运行时，在单独终端启动 Worker。
.\.venv\Scripts\python.exe -m app.worker
```

重启直接重新执行启动脚本，已有数据库保留。备份时先正常停止前后端与 Worker，复制完整 `storage`（包括 WAL/SHM），并单独保管 `.env`；恢复到新位置，不覆盖现有数据。Worker 对同一数据库持有进程锁，重复启动会退出；锁文件无需删除。

生成中断后，有远端编号的任务继续查询。提交结果不明时到订单下方记录核对依据并关联远端任务，或在确认未受理后补生成；接受可能重复计费须明确勾选。下载/落盘失败点击“恢复原任务”，不会重新生成。费用没有供应商依据时显示“未知”。

阶段 3 验收记录见 [stage3-validation.md](docs/stage3-validation.md)。隔离工具 `python scripts/stage3-qa.py` 仅准备专用绘图测试单；`--live --seconds 45` 才处理真实任务。默认目录 `storage/qa-stage3-20260920` 已有成功结果，再运行不会自动新建一组；未明结果也不会自动重发。使用独立目录开展新测试会新建任务，真实模式可能产生费用。

生成成功后点击“继续修改”，填写本次要求；基础图及按位置指定的素材一同作为模型输入。修改成功自动更新结果，“版本历史”可切回；补生成不增加修改轮次。

下载不自动完成。完成要求有效当前交付图及无未结束任务；关闭不要求有图。完成/关闭后只读，仍可下载。当前交付图不能直接作废。

本地模拟浏览器验收（不访问真实供应商）：在根目录执行 `.\.venv\Scripts\python.exe scripts/browser-qa.py --root storage/qa-browser-20260921`；另开 PowerShell，在 frontend 设置 `$env:AIFACE_BACKEND_ORIGIN='http://127.0.0.1:18000'`、`$env:AIFACE_NEXT_DIST_DIR='.next-browser-qa'`，再运行 `npm run dev -- --port 13000`。现有验收目录保留已完成记录；要新跑场景，使用新的 storage/qa-* 目录。服务均可 Ctrl+C 停止，停止后恢复 tsconfig/next-env 的默认 `.next` 类型路径，保留测试文件。详情见 [阶段 4 验收](docs/stage4-validation.md)。

## 验证

2026-09-21 UI 修改包 1.0.0 已备份应用，并修复跨页锚点高亮。前端 51 项测试、类型检查、ESLint 和生产构建通过；修复后 35 项相关测试及最终构建通过，另有 24 项后端回归通过。Chrome 验证导航、四图/窄屏、单图生成、修改、切回版本、只读下载、草稿恢复及提交不明核对；4 次本地模拟 submit，真实供应商 POST 0 次。具体覆盖边界、备份位置及服务状态见 [UI 修改包验收](docs/ui-fix-validation.md)。

2026-09-21 阶段 5：后端 88 项、前端 10 项、Ruff/格式、ESLint、TypeScript、pip check、生产构建和 Alembic check 通过。单图交付浏览器结果见 [阶段 5 验收](docs/stage5-validation.md)。真人及真实修改效果仍待阶段 6；本次真实供应商提交 0 次。阶段 4 的 14 次本地模拟调用属于历史验收。

```powershell
.\scripts\check.ps1
.\scripts\check.ps1 -Build
.\scripts\start-dev.ps1 -SmokeTest
```

检查覆盖后端 Ruff、格式、pytest、依赖一致性，以及前端 ESLint、TypeScript、请求封装测试；`-Build` 额外执行生产构建。冒烟模式实际启动前后端，检查首页和同源健康接口，随后自动停止本次服务。

2026-09-20 阶段 2 已通过：后端 44 项、前端 6 项测试，lint、类型检查、生产构建、迁移对齐、并发素材限制、应用重启保留数据，以及桌面/390px 窄屏界面检查。13 MiB 同源上传成功且图片内容完整，20 MiB+1 返回 413。浏览器自动文件选择受扩展权限限制，上传链路使用同源 HTTP 验证；真实模型验证尚未执行。

图片依赖锁定 Pillow 12.2.0、python-multipart 0.0.32。曾遇到 Pillow 12.3.0 下载不完整且哈希校验失败，未跳过校验；12.2.0 从官方 PyPI 成功安装。依赖恢复继续使用锁文件。

当前工具链限制：Next.js 16.3.5 携带的 React ESLint 插件在 ESLint 10 下报错，暂固定 ESLint 9.39.5（npm 提示已停止维护）；安装审计为 0 个已知漏洞。后端测试目前有来自 Starlette/httpx 和 AnyIO 的两条弃用提示，测试通过，未隐藏警告。

Windows PowerShell 5.1 的中文 `.ps1` 文件使用 UTF-8 BOM，避免默认 ANSI 解码导致乱码和语法错误。

设计与进度见 [实施计划](docs/implementation-plan.md)、[架构](docs/architecture.md)、[API](docs/api.md) 和 [验收记录](docs/acceptance.md)。
