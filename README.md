# AIFACE 头像工作台

商家内部使用的头像接单工作台，首版固定蜡笔风格。输入最多 4 张，首次生成 1 张直接交付，每次修改 1 张；修改轮次仅记录，不设置系统硬上限。

当前已实现阶段 5：首次生成一张交付图，修改成功自动替换，失败保留原图；历史版本可切回，下载当前单张原图，再独立确认完成或关闭订单。旧双图订单保留历史，须手动指定其中一个版本交付。真实人物/风格及修改效果仍待阶段 6；本次未新增真实供应商调用。首页插画为 CSS 示意图。

## 本地启动

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
| `AIFACE_DATABASE_PATH` | SQLite 路径，默认 `storage/database/aiface.sqlite3`；相对路径始终以项目根目录为基准 |
| `AIFACE_STORAGE_PATH` | 素材根目录，默认 `storage`；隔离测试时与数据库路径一起设置 |

前端不读取根目录 `.env`，通过 Next.js 将同源 `/api` 转发到 `127.0.0.1:8000`。数据库使用外键、WAL 和 5 秒锁等待；不在 API 启动时自动建表。当前迁移 head 为 `0005_single_generation`；0004 增加交付历史，0005 允许新单图并保留旧双图任务。上传支持 JPEG、PNG、WebP 静态单帧，最多 20 MiB、4000 万像素。

页面入口：`/orders` 订单列表、`/orders/new` 新建。详情中上传主照片、选择发型和服装来源、保存创作要求，再检查待生成。当前素材最多 4 张，主照片/参考图各最多 1 张；切换主照片会将旧主照片转为辅助。移出素材会清空受影响来源，文件保留；恢复后需重新选择来源。未保存的参数可撤销。准备好订单不会调用模型或产生费用。

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

生成成功后在“当前交付图”点击“修改这张图”，填写本次要求；基础图占 1 个输入名额，附加素材手动选择且最多 3 张。沿用基础图风格版本，本次指令优先于旧控制项。修改成功自动更新当前图，“版本历史”可切回；补生成不增加修改轮次。

下载不自动完成。完成要求有效当前交付图及无未结束任务；关闭不要求有图。完成/关闭后只读，仍可下载。当前交付图不能直接作废。

本地模拟浏览器验收（不访问真实供应商）：在根目录执行 `.\.venv\Scripts\python.exe scripts/browser-qa.py --root storage/qa-browser-20260921`；另开 PowerShell，在 frontend 设置 `$env:AIFACE_BACKEND_ORIGIN='http://127.0.0.1:18000'`、`$env:AIFACE_NEXT_DIST_DIR='.next-browser-qa'`，再运行 `npm run dev -- --port 13000`。现有验收目录保留已完成记录；要新跑场景，使用新的 storage/qa-* 目录。服务均可 Ctrl+C 停止，停止后恢复 tsconfig/next-env 的默认 `.next` 类型路径，保留测试文件。详情见 [阶段 4 验收](docs/stage4-validation.md)。

## 验证

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
