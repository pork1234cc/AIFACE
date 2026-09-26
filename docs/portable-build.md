# Windows 便携版

## 最新：2026-09-26 22:39 图片接口与刷新修复版

- 分发：`dist/AIFACE-0.1.0-Windows-x64-Portable-RefreshFix-20260926-223955.zip`，190,741,127 字节（约 182 MiB），2,545 个文件。SHA256：`9a2335b17bd14d1b10bdcd3aa9a7d4931fa0a4228fb07ebce1bd8814b42d7349`。
- 包含三模型切换、纯文生图、遮罩、自定义比例/尺寸、同步/异步与 URL/Base64 返回。交付图和任务详情独立轮询，交付读取采用一致快照，查询异常显示下次查询时间，详见 [刷新修复](refresh-delay-review.md)。
- 后端277项、前端83项测试、Ruff/ESLint/TypeScript及前端生产构建通过。8个模块编译和五步打包流水线通过，源码哈希核对及编译产物归档完成；构建临时改动的前端配置已还原。
- 最终 ZIP 的 CRC、私人数据排除检查通过。EXE 归档确认包含新 Base64 处理模块及修复后的交付接口；静态前端包含刷新修复和三模型选项。
- 从最终 ZIP 解压到独立中文路径，隔离用户目录，PATH 仅保留 Windows 系统路径；实际 EXE 空库迁移、前端、同源 API、授权门禁、两类本地模型 CPU 推理通过，退出后18480/18481端口释放。
- EXE SHA256：`08dd4a55f05f3e260c97aa1d7ba12e64354ba98e859ef01ed1c9654f639eaed2`。构建及验收记录：`outputs/build-records/20260926-223955/`；流水线日志：`storage/logs/portable-refresh-build.log`。
- 限制：本机隔离验收，没有直接操作朋友电脑或使用独立 Windows 虚拟机；未调用真实生图服务、Codex 或卡密激活。

升级步骤：等待现有任务结束并退出旧程序，完整解压新 ZIP 到新目录；将旧程序目录的 `storage`、`.env`、`codex-settings.json`（存在时）复制到新目录中的 `AIFACE` 文件夹，然后运行新 `AIFACE.exe`。保留旧目录作为备份，不要只替换 EXE。原 `.env` 会保留 API 配置和模型选择。

以下为历史版本记录。

## Codex 元素识别版构建

### 最新：2026-09-26 21:48 路径配置版

- 分发：`dist/AIFACE-0.1.0-Windows-x64-Portable-Codex-20260926-214825.zip`，190,730,399 字节（约 182 MiB）。SHA256：`62e5b7f524ca3322d2b873f4bbd22fcf3b5adfe1fae78033f669d9db48cd68d8`。
- 模型设置新增 Codex 路径输入、系统浏览、自动检测及独立保存。优先手动路径，空值查找 PATH、常见桌面版及 npm/商店目录。路径写入 `codex-settings.json`，随程序可写目录保存，不分发开发机路径。
- 后端 220 项、前端 75 项测试、Ruff/ESLint/类型检查通过；本机 PATH 移除后实际检测桌面版成功，浏览器保存、刷新恢复、无效路径及恢复自动检测通过。修正了既有回归测试受本机生图模型配置影响的问题，正式 `.env` 保持不变。
- 流水线和源码恢复检查通过，归档含 `codex_runtime`、`tkinter.filedialog` 及 `_tkinter.pyd`；最终 ZIP 中文路径、隔离用户/系统 PATH 下 EXE 启动和双模型推理通过，退出释放端口。ZIP CRC 与私人数据检查通过，旧 ZIP 保留。
- EXE SHA256：`0b00c504de6e76cd3502dd7ba5ffd09e71b3523992c56f13a90e60084a1b8a3c`；记录在 `outputs/build-records/20260926-214825/`，日志 `storage/logs/portable-codex-path-build.log`。
- 浏览窗口选择/取消与冻结子进程分支已自动测试；本轮未自动操作原生文件窗口，未调用图片模型或真实激活，未使用独立 Windows 虚拟机。

新增 MobileSAM 编码器、解码器白名单资源及作者许可，保留原人像区域模型。便携 EXE 冒烟同时验证两类模型实际 CPU 推理；对象轮廓检查使用合成矩形，不上传照片、不调用 Codex。

目标电脑无需安装 Python、Node 或 CUDA。自动对象分析需要安装 Codex CLI 或附带 CLI 的桌面版并登录，支持自动检测和模型设置页手动指定，使用目标用户自己的权限和额度；Codex 程序及其登录凭证不随包分发。已缓存对象的选择及轮廓修正只需本地模型。配置、订单、图片与开发机凭证继续排除在包外。

构建采用独立时间戳目录和新 ZIP 文件名，保留已有便携包。

### 2026-09-26 21:28 构建验收

- 新包：`dist/AIFACE-0.1.0-Windows-x64-Portable-Codex-20260926-212840.zip`，190,701,244 字节（约 182 MiB），完整解压后运行 `AIFACE/AIFACE.exe`。
- ZIP SHA256：`dc9786e1431ac8e6b1cd4804bc01412fa7cf6fafe4b1776b84d38f2219e8009b`；EXE SHA256：`3ff94a40a5788ecaa0cc26681b762f7e780d9863428a9a861cc9f57698c93915`。
- 项目 `.venv` Python 3.12.14，30 项相关测试和改动文件 Ruff 通过；前端生产构建、8 个模块编译及打包流水线成功。源码哈希与原地编译产物归档检查通过，没有本轮 PYD/C/备份残留。
- 从最终 ZIP 解压到 `storage/qa-portable-20260926-212840/中文 便携验证`，隔离用户目录，PATH 仅保留 Windows 系统目录；实际 EXE 空库、前端、同源 API、授权门禁及两类模型 CPU 推理通过，业务表为空，退出后端口释放。
- 归档包含新元素接口、Codex 子进程、任务缓存和分割模块，两个 MobileSAM 文件与源文件哈希一致。2,543 个文件，ZIP CRC 通过；没有私人配置、登录凭证或业务库。构建告警仍是未使用的 `tzdata/pysqlite2/MySQLdb` 可选依赖，没有缺失 DLL 告警。
- 记录：`outputs/build-records/20260926-212840/manifest.json`、`validation.json`、`smoke.log`；流水线日志：`storage/logs/portable-elements-build.log`。
- 限制：本机隔离验收，未使用独立 Windows 虚拟机；本轮未调用 Codex 或生图服务、未执行真实卡密激活。Codex 图片分析此前已在源码版用真实样图验证，目标电脑仍需自行安装并登录 CLI。

以下为此前版本的历史构建记录。

2026-09-26：已生成并验收 Windows x64 便携版。分发 `dist/AIFACE-0.1.0-Windows-x64-Portable-20260926.zip`，完整解压后双击 `AIFACE/AIFACE.exe`。

## 设计与分步实施

1. `AIFACE.exe` 默认启动完整工作台；保留 api、worker、migrate 服务子命令。自动迁移空库，启动本地 API、独立 Worker 和 Next.js standalone，再打开默认浏览器。
2. 使用固定本机端口 18480/18481，与开发端口隔离；端口被占用时明确退出，不结束其他进程。启动器管理自己的进程；Windows Job 在启动器退出时回收其子进程。
3. Node.js 和前端生产文件随包携带，目标机不需要 Python、Node.js、npm 或 CUDA。后端由当前项目虚拟环境构建。开发和线上前端构建保持原样，便携前端使用独立 `.next-portable`。
4. 首次运行只创建不含模型密钥的默认配置，数据库、照片与日志写入解压目录；内置风格及约 51 MiB 区域模型随包提供。用户需要有效软件授权以及自己的模型 API 配置。卡密类型由服务器决定，本次不修改授权类型、缓存、产品 ID 或有效期。
5. 使用宿主自定义 PyInstaller 文件夹 spec 与现有 commenlib 流水线。原组件不升级。旧流水线缺少产物清单，宿主构建助手记录源码/产物哈希，并在编译成功后把可确认的原地 PYD 移出源码目录保存到构建记录，避免删除未知文件。
6. 分发包仅收集白名单资源，排除私人 `.env`、凭证、订单库、照片、测试与开发环境。保留第三方许可文件。

## 验证要求

- 修改模块后先 lint 和受影响测试，再执行流水线。
- 核对 EXE、前端、Node 和模型资源及构建哈希，检查归档模块。
- 在独立中文路径解压副本，使用隔离 APPDATA、清除 Python/Node 环境变量与 PATH 依赖，执行实际 EXE 冒烟；不运行 Worker，不调用授权激活或付费生图。
- 测试后保存验收数据，发布 ZIP 从未运行的干净目录生成，不把测试数据压进去。
- 无独立干净 Windows 虚拟机时明确报告测试限制，不用本机测试声称全部 Windows 环境验证通过。

## 本次构建与验收

- 构建环境：项目 `.venv`，Python 3.12.14 / cp312-win_amd64、Cython 3.3.0、PyInstaller 6.22.3、MSVC 14.44、Windows SDK 10.0.26100.0；前端使用 Next.js standalone，随包 Node.js 22.23.2。
- 改动文件 lint、48 项受影响测试、公共组件原始快照哈希核对通过。最终 ZIP 154,015,217 字节（约 147 MiB），SHA256 `be1bc043e8c59509c67e1be5ef5ff0f84318683c1f3e070db24652025ad31f1e`。
- 宿主 `services` 是命名空间包，原通用 Cython 自动推断把 `licensing` 放到了顶层。已通过失败用例确认；宿主构建适配显式指定 `app.services.licensing`，按完整模块名生成后再复制到对应源码目录，公共组件原文件不修改。失败产物核对哈希后归档。
- 8 个模块完成编译；EXE 依赖分析实际收集宿主授权 PYD 与 6 个组件 PYD，未用的单实例组件不进入分发包。归档检查确认 API、Worker、配置和启动器存在，授权宿主以 PYD 提供，不作加密承诺。
- 实际 EXE 位于 `storage/qa-portable-20260926/中文 便携验证/AIFACE`，APPDATA 指向独立空目录，PATH 仅保留 Windows 系统路径。退出码 0；前端首页、同源 API、未激活业务接口 403、空库迁移、ONNX 模型 CPU 推理均通过；退出后 18480/18481 无监听残留。未启动生成 Worker、未激活新卡、未调用付费生图。
- 分发目录不包含私人 `.env`、授权缓存、机器码缓存或业务数据库；默认 API Key 为空。Python、Node、依赖与区域模型许可随包提供。
- PyInstaller 的 `tzdata`、`pysqlite2`、`MySQLdb` 警告为未使用的可选依赖；当前使用本机时间和内置 sqlite3，实际数据库迁移正常。没有缺失 DLL 警告。
- 本轮源码哈希恢复核对通过，原地 PYD 和专用工作目录已按清单移到构建记录，源目录没有本轮 PYD/C/备份残留。未删除未知文件。
- 完整清单、EXE/ZIP SHA256 和验证记录见 `outputs/build-records/20260926-172414/`；日志见 `storage/logs/portable-*.log`。ZIP 已逐项 CRC 校验。
- 限制：没有独立干净 Windows 虚拟机；当前证据是 Windows 11 本机隔离环境验收。真实卡密激活、供应商生图与其他 Windows 版本兼容性不在本轮测试内。

## 后续重复构建

使用当前项目虚拟环境执行 `commenlib/buildsystem/build_all.py --config build_config.yaml`，依次准备、编译、打包、组装、归档。助手输出到独立时间戳目录，校验源码/编译产物哈希，并拒绝覆盖已有产物。最终只压缩未运行的 `AIFACE` 目录；不要压入验收副本。
