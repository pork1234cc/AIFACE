# 公共组件接入

日期：2026-09-26。状态：代码接线完成；产品映射已按用户最新要求修正为 `aiface` → `小红书头像工作台`，新产品尚未真实联网验证。

## 2026-09-26 产品映射修正

`project.yaml` 的 `license.product_id` 改为 `aiface`，`app.name` 改为 `小红书头像工作台`，安装记录同步修正。凭证目录随产品 ID 变为 `%APPDATA%/aiface`，旧目录保留，不复制旧产品凭证。参考项目只能用于核对服务地址，不能据此推断本项目的产品 ID 或名称；下方 `xhstupian` 联网验证记录仅为历史证据。

先修改现有配置回归测试，确认旧 ID 导致失败，再修正配置；24 项授权运行时/API/Worker 测试及测试文件 Ruff 检查通过，安装记录 JSON 解析通过。未调用真实激活或验证接口。既有便携包仍为旧配置；用户随后要求仅重启、不打包。

已按要求重启后端、Worker 和 3000 开发前端，新启动器 PID 33544。重启前确认 3 个生成任务与 2 个示意图任务全部成功，仅结束经命令行核对的原启动器进程树。8000/3000 健康检查、3000 首页均返回 HTTP 200，授权接口显示 `小红书头像工作台`、`authorized=false`，需使用 `aiface` 对应卡密激活，Worker 正常等待授权。3001 原本未运行，本次未启动；Tunnel 保持运行。未构建、未打包、未提交激活请求。

## 2026-09-26 17:06 配置修复与联网验证

依据用户提供的 `E:/2-AI/小说图片生成/project.yaml` 和接入文档，确认同一产品 `xhstupian` 的授权地址为 `https://xhstools-qedmuqoouc.cn-hangzhou.fcapp.run`。仅只读查看该项目。AIFACE 原始配置字节已备份为 `project.yaml.9b4287bfa40f4d949c03f62479d8ca89.bak`，随后只替换服务地址，产品 ID 与盐值不变。

配置回归测试先失败、修复后通过，授权运行时和接口/Worker 共 24 项测试通过，改动文件 lint/格式通过。确认无进行中任务后，按 PID 和完整命令行核对原启动器，仅停止其进程树并重新启动本项目。新启动器 PID 29264，8000/3000 健康检查均为 200。

现有本机凭证自动向正确服务完成联网验证：`authorized=true`，有效期 `2026-10-26 16:28:34`，Worker 日志确认“授权通过，生成 Worker 已启动”。未再次提交激活请求，未在日志或文档记录卡密。页面刷新即可进入。生产前端 3001 的原启动限制未在本次处理。

## 2026-09-26 激活失败诊断

用户反馈无法激活。后端日志出现 JSON 解码错误 `Expecting value: line 1 column 1 (char 0)`。对配置地址的 `/activate` 发送一次不含卡密、机器码的空 JSON 探测，得到 HTTP 400 和 XML：`OTSUnsupportOperation` / `Unsupported operation: 'activate'.`。当前地址是 OTS 数据库接口，不支持组件的激活操作；不能据此判断用户卡密无效。需要改为已部署授权程序实际提供 `/activate` 和 `/verify` 的 HTTP 基地址，不需要重新部署。

原宿主适配丢弃了组件的错误原因，页面只显示笼统的“授权未通过”。已先添加 10 个失败回归用例复现，再修复为固定安全提示，区分非 JSON 响应、连接失败、超时、卡密无效和过期等原因；不回显上游原文或用户卡密。授权相关 24 项测试及改动文件 lint/格式检查通过。配置和提示修复均已生效，见上方 17:06 验证记录。

教训：用户确认“已经部署”不等于客户端 URL 与组件协议已核验；应使用不带凭证的接口探测验证协议，并保留安全的错误分类，避免把接口错误显示成卡密问题。诊断中未使用、记录或向错误地址发送用户提供的卡密。

## 2026-09-26 16:55 重启记录

用户要求重启。检查时 3000/3001/8000 服务均已停止，正式库 3 个生成任务与 2 个风格示意图任务均为 succeeded，无待处理任务。使用项目 `.venv` 启动 `scripts/start-dev.ps1`，启动器 PID 37004；后端 8000、本地前端 3000 健康检查均通过，首页 HTTP 200 且包含激活入口，Worker 进程已启动并等待授权。目前授权状态为未通过，未提交新的激活请求。

生产前端 `.next-mobile` 已重新构建成功，但启动 3001 进程被自动审批拒绝（`blocked by policy`，未提供具体原因）。因此本次仅完成后端、Worker 和本地前端启动，3001 仍未恢复；既有 Tunnel（PID 9956）保持运行，外网入口仍依赖 3001。下方原接入阶段“未重启”记录为历史状态，以本节为准。

## 已确认配置

- 授权名称：小红书头像工作台；保留 AIFACE 业务页面与产品流程。
- 产品 ID：`aiface`，以用户最新纠正为准，凭证目录为 `%APPDATA%/aiface`。
- 授权服务：`https://xhstools-qedmuqoouc.cn-hangzhou.fcapp.run`，来源为用户提供的正常软件配置。
- 原 OTS 地址为数据库入口，已修正；沿用现有 `/activate`、`/verify` 协议，不新增服务部署。旧产品凭证曾真实联网验证通过，`aiface` 尚未实测。
- 本次仅安装、适配和预检，不编译、不打包、不部署服务端。
- 未提供更新地址，不启用更新入口；不新增单实例功能。

## 接线设计

1. 安装 Skill 自带原样组件，依赖合并到后端声明与锁文件。
2. 根目录 `main.py` 为 Python 入口，支持 API、Worker 与数据库迁移；现有启动脚本使用此入口。
3. FastAPI 使用 `LicenseClient` / `LicenseGuardConfig`，通过线程池执行同步验证，不使用 Tk helper。配置缺失和异常均不放行。
4. 网页根布局先显示授权门禁，成功后挂载原业务界面。业务 API 在服务端拦截，健康检查与授权端点可以在未激活时访问。
5. API 进程统一维护授权客户端，避免 API 与 Worker 同时改写凭证。Worker 通过本机 API 获取授权状态，失联或未授权时不创建业务 Worker、不领取任务；授权失效后暂停后续步骤，保留任务恢复语义。
6. 首次已有凭证联网验证；成功激活复用同一客户端。每小时检查一次距上次联网验证的时间，满 24 小时重新验证，永久卡也参加；请求时同时检查到期和时间回拨。周期失败后封锁业务，允许重新激活。
7. Python 构建范围只包含宿主运行模块、迁移、风格与识别模型，不收集私人 `.env`、业务数据、测试目录或整仓库。完整前端便携运行环境在后续打包任务准备。

## 实施批次

- 批次一：组件安装、入口骨架、运行依赖与配置。
- 批次二：授权运行时与模拟测试，然后 API / Worker 接线与回归。
- 批次三：网页授权门禁与前端验证。
- 批次四：构建预检、文档与安装标记证据。

每个批次按模块运行 lint 和受影响测试。模拟测试不读取真实授权凭证、不访问真实授权服务器、不提交付费生图。

## 验证记录

使用项目 `.venv` Python 3.12.14。安装 requests 2.34.2、PyYAML 6.0.3 及其缺失依赖，声明与锁文件已同步，`pip check` 通过。后端 editable 安装使用项目原有隔离构建方式；未向全局 Python 安装依赖。

- 授权运行时/API/Worker 14 项专项测试通过，涵盖首次验证、激活成功/失败、永久卡周期校验、撤销、过期、时间回拨、客户端复用、异常不放行、接口卡密脱敏、Worker 等待/暂停/退出，以及组件兼容的分钟精度到期时间。
- 后端完整 169 项测试通过；测试专用 `conftest.py` 注入模拟授权，生产代码没有免授权配置开关。专项测试显式注入拒绝/允许的运行时。
- 前端 70 项测试、ESLint、TypeScript 与隔离生产构建 `.next-license-qa` 通过。构建自动添加的 TypeScript 隔离目录已恢复，不覆盖正在使用的前端构建。
- Skill `verify.py` 通过组件快照哈希、Python 语法与宿主四步流水线 dry-run；未执行 Cython、PyInstaller、构建清理或真实模型调用。
- 组件原样文件 `singleinstance_guard/__init__.py` 存在 `invalid escape sequence` 语法警告，不影响本次检查；未改动组件快照。本次未启用单实例功能。
- 隔离模拟 API 曾启动，已按本次进程 ID 与命令行核对后停止。验收资料保留在 `storage/qa-commenlib-20260926`。
- 启动隔离前端进程被自动审批拒绝（`blocked by policy`，未提供更具体原因），未执行浏览器实测。未以构建或模拟测试声称浏览器验收通过。
- 未重启原有后端、Worker、生产前端或 Tunnel；运行中的旧进程不作为新授权流程的验证证据。

复验命令（项目根目录）：

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe -m ruff check backend main.py
.\.venv\Scripts\python.exe -m pip check
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend test
.\.venv\Scripts\python.exe -B -X utf8 C:/Users/Administrator/.agents/skills/commenlib-integrate/scripts/verify.py --project E:/2-AI/AIFACE
```

## 入口与 API

- 开发入口 `start-aiface.cmd` → `scripts/start-dev.ps1` → `main.py migrate/api/worker`，需要项目开发环境。冻结入口 `AIFACE.exe` 默认进入 desktop 模式，管理随包前后端及 Worker；便携使用方法见 [便携版说明](portable-build.md)。后端不启用热重载，改代码后需正常重启。
- 直接运行 `python -m uvicorn app.main:create_app --factory` 同样受业务 API 门禁保护；`python -m app.worker` 使用本机授权 API。API 与 Worker 必须使用相同端口，Worker 可传 `--api-port`，统一入口可传 `--port`。
- `GET /api/license/status` 返回 `authorized/name/message/expire_time`；`POST /api/license/activate` 接受 JSON `code`；`POST /api/license/verify` 复验现有凭证。授权响应禁止缓存，不回显卡密和机器码。激活或复验失败返回 403。
- 未授权业务请求返回 403、`error.code=license_required`。`/api/health` 和三个授权端点可访问，文档和其他业务路径均受拦截。页面根布局在授权通过前不挂载原工作台，授权状态每分钟刷新。
- Worker 在当前任务步骤结束后再查授权；撤销或失联时不执行后续步骤，已有请求结果按原流程保存，避免强杀造成提交结果不明。退出仍由原启动器管理。

## 打包边界和后续事项

`project.yaml` 配置了 Python 服务入口、宿主授权模块的 Cython 范围、动态导入和明确资源。源码运行路径不变；冻结运行时从打包资源目录读取风格、模型与迁移，`.env` 和业务数据写入 EXE 所在目录。压缩包应解压到可写目录。

安装器自带流水线为旧版，不含 Cython 产物哈希清单。2026-09-26 便携构建已通过宿主 `build_config.yaml` 和 `scripts/portable-build.py` 补充精确清单、命名空间编译适配、源码恢复校验及可恢复归档；不改公共组件文件。实际源码扫描和 EXE 检查均已完成，详见便携版记录。

已有便携包包含 Next.js standalone、Node.js、Python EXE、本地模型和统一启动/退出管理，并通过 Windows 11 隔离用户目录实际 EXE 冒烟；尚无独立干净 Windows 虚拟机验证。该包使用历史产品 `xhstupian`，本次修正为 `aiface` 后需要重新构建。历史本机凭证的真实复验不代表新产品通过验证；打包时未重新激活新卡、未复制已有凭证。卡密授权与生图 API Key 是两套配置。
