# Codex 图片元素拆解

2026-09-26：源码版已用 Codex 动态对象分析 + 本地 MobileSAM 独立蒙版替代网页固定人像类别选择。旧 `/regions` 接口保留兼容，不再由新网页调用。

## 使用

1. 安装并登录 Codex CLI，或安装附带 CLI 的 Codex 桌面版。模型设置页会自动检测 PATH、常见桌面版及 npm 目录；也可在“Codex 程序路径”中粘贴绝对路径或点击“浏览…”选择 `codex.exe`，再点击“保存 Codex 设置”。清空路径保存即恢复自动检测。子进程沿用启动 AIFACE 用户的模型与登录配置，不使用生图 API Key。
2. 源码版在项目根运行 `.\.venv\Scripts\python.exe scripts/install-element-model.py`。复用已有 NumPy、Pillow、ONNX Runtime，无需 CUDA。20260926-212840 便携包已内置模型，无需此步骤。
3. 打开订单，保存主图片后点击“识别图片元素”。完成后从对象树或图片选择元素，填写要求与素材用途并保存。
4. “放大点选”支持 50%～200% 缩放和滚动，优先选择细节，可切换重叠候选或选择上级。选区不准时先选对象，再使用“补选范围／排除范围”点击修正。

首次识别将当前图片作为附图交给 Codex，可能耗时数分钟；轮廓分割在本机完成。刷新只读取缓存，不重复调用模型；失败保留旧结果和文字，不退回固定类别伪装成功。单图最多 100 个候选，修改要求容量也提高到 100 项。新版便携 ZIP 内置 MobileSAM；源码版与便携版都需要本机已安装且登录的 Codex CLI。分发及验收见 [便携版说明](portable-build.md)。

## 路径检测与本机浏览

查找顺序：已保存手动路径 → PATH → 常见桌面版目录 → npm/商店目录。手动路径无效时明确报错，不自动切换。自动候选逐一验证 `--version` 和 `exec --help`，验证结果按文件修改时间及大小缓存；不调用模型、不验证登录。npm 脚本入口转换为包内原生 EXE，不以 shell 执行脚本。

路径配置在可写根目录 `codex-settings.json` 原子保存，与生图 API 配置独立，下一次识别立即读取；不随便携包分发。保留安装入口符号链接，避免固定到某个历史版本的二进制。桌面版路径不受官方稳定性保证，未知安装位置可手动指定。

“浏览…”由独立 `AIFACE.exe select-codex`（源码版为项目 Python + main.py）打开系统文件选择窗口；取消不改变输入，选择后仍需保存。浏览 API 仅允许本机来源，远程页面须回到运行 AIFACE 电脑的本机网址使用浏览。选择窗口 180 秒超时，可粘贴路径代替。检测到 CLI 不代表已经登录或有模型额度。

## 子进程与接口

网页已接入 `codex exec --image ... --output-schema ... --output-last-message ...`，使用参数数组、只读沙箱、UTF-8 标准输入输出及 360 秒超时。最终 JSON 必须通过坐标、容量、唯一 ID 和父子关系验证；返回内容不会作为命令执行。

```powershell
# 调用 Codex；输出文件必须使用新路径。
.\.venv\Scripts\python.exe scripts/analyze-elements.py --image "C:\path\photo.png" --output "storage\element-import.json"
# 导出供自建 Codex 子进程使用的 output-schema。
.\.venv\Scripts\python.exe scripts/analyze-elements.py --schema "storage\element-schema.json"
# 使用已有 Codex objects JSON，不再次调用模型。
.\.venv\Scripts\python.exe scripts/analyze-elements.py --image "C:\path\photo.png" --analysis "storage\objects.json" --output "storage\element-import-2.json"
```

接口根路径：`/api/orders/{order_id}/images/{asset_id}/elements`。

| 方法与路径 | 行为 |
| --- | --- |
| GET 根路径 | 只读进度与缓存，不启动推理 |
| POST 根路径 | 启动 Codex + 分割，返回 202；同图运行中复用任务 |
| POST `/import` | 正文 `{image_sha256, analysis:{objects:[...]}}`，仅运行本地分割 |
| POST `/{region_id}/refine` | 正文 `{version,points:[{x,y,label}]}`，label 1 包含、0 排除 |

接口验证订单图片归属、当前底图及软件授权，写操作拒绝归档订单。导入 SHA256 必须匹配资产实际内容，建议先从资产 content_url 下载图片。每次修正 1～16 点，单元素累计最多 32 点；人工相反点优先于旧提示，包含点可以扩展原框。旧 version 返回 409，防止并发覆盖。每进程串行分析/修正，其他图片占用时返回 409 `element_busy`。

读接口返回 `asset_id,status,message?,result?`，status 为 idle/running/ready/failed；失败重识别可同时返回上次成功结果。缺 CLI、登录失败、超时或坏 JSON 通过任务 failed/message 显示，不暴露 CLI 原始 stderr、凭据或路径。

## 对象与蒙版

### 元素名称排列（2026-09-26）

网页元素名称采用按内容宽度排列的标签，按原识别顺序从左到右自动换行，不固定列数。取消子元素左侧层级缩进，保留 `↳` 标记、选中状态及“待定位／已填写”提示。标签最大宽度限制在容器内，超长名称在标签内部换行，最小点击高度 36px、间距 8px；识别列表仍限制为 360px 高并支持滚动。手动补充与保留的旧元素名称同样支持长文本换行。

验证：相关 9 项前端测试、组件 ESLint、TypeScript 与 CSS 语法检查通过。Chrome 使用现有 100 项识别结果验收：桌面列表宽 548px 时大多数行显示 3 项，390px 手机视口下列表宽 310px、前 12 行均显示 2 项，无标签或列表横向溢出；已填写元素点击后选中及编辑字段正常显示。

Codex 对象字段：`id,parent_id,label,target_description,kind,bbox,positive_points,negative_points`。kind 为 object/part/detail/background；中文名称来自实际图片，不预设类别表。框 `[x1,y1,x2,y2]` 和点 `[x,y]` 均相对整图归一化到 0～1000。拒绝重复 ID、循环/丢失父级、非法框及越界坐标。

结果字段：`schema_version:1,version,provider,image_sha256,width,height,regions`。每个 region 含实例 ID、父级 ID、名称、目标描述、深度、框、`mask_runs,mask_area,mask_score,location_status`。mask_runs 为按行展平的前景 `[起点,长度,...]`，索引基于结果 width/height，长边最多 1600px。蒙版可独立重叠，点选优先更深的细节并保留父级/重叠候选。低分或明显异常面积的候选显示待定位，不用矩形框冒充轮廓。mask_score 为分割模型分数，不是语义准确率。

缓存位于存储根 `element-analyses/{order_id}/{asset_id}`。每次结果独立留档、current 原子更新。重新分析生成新实例 ID，旧文字不自动绑定新实例；修正轮廓保留实例 ID 并更新 version。网页已写文字继续存入 region_prompts，无数据库迁移。

模块：`services/elements.py`（契约/提示词）、`codex_elements.py`（子进程）、`element_masks.py`（分割）、`element_jobs.py`（任务/缓存）、`api/elements.py`（HTTP）。

蒙版用于点选、高亮和修正，不进入生图请求；生成仍使用对象位置描述、要求和素材。不能承诺选区外像素完全不变，也不还原不可见的原始图层。遮挡、小纹理和模糊边缘可能需要人工修正。

## 验证

- 路径配置新增 11 项测试覆盖手动优先、错误路径不切换、清空恢复自动、桌面版/npm 发现、探测失败/超时、API 保存、本机浏览限制、取消及冻结子进程入口。后端全量 220 项、前端 75 项、lint 与类型检查通过。既有生图回归发现本机 `.env` 模型干扰，已在测试 fixture 固定测试模型，无需改变正式配置。
- 本机实际验证移除 PATH 的 Codex 后仍由桌面版目录发现。Chrome 验证手动路径保存/刷新、无效路径提示、恢复自动检测及页面布局；当前默认保留自动检测。系统对话框返回与取消采用自动测试验证，本轮没有自动操作原生文件窗口；未再次调用模型。

- 用户双人插画真实调用 Codex 一次，输出 97 项，约 5 分钟；CPU 分割约 9.64 秒。候选数不是准确率，耗时仅代表本机样本。
- 抽查两个人头发、上下蝴蝶结、两只兔子、顶部爱心、嘴部的叠加图，轮廓分别定位。
- Chrome 隔离实测关键对象独立命中、50% 缩放对齐、空白命中背景、补选调用、单元素要求保存/刷新恢复及组合提示词。未调用生图供应商。
- 前端 75 项测试、ESLint、TypeScript、生产构建通过。后端完整回归 207 项通过，追加人工修正优先测试后 18 项相关测试通过；改动 Python 的 Ruff/格式及 pip check 通过。
- 自动测试覆盖动态实例、空图、非法层级/坐标、蒙版空洞、细节优先、缩放边界、97 项保存、子进程失败、图片归属/摘要、缓存、修订冲突及重识别 ID 隔离。
- 验收数据保留于 `storage/qa-elements`，包括 Codex JSON、导入正文、蒙版叠加图及隔离库。未清理正式数据；真人和其他题材尚未开展真实 Codex 质量评测。
- 运行更新：确认正式库生成任务 3 项、风格预览 2 项均已成功，无进行中任务后，重启 8000 后端、3000 开发前端及 Worker。健康检查为 ok，新增元素接口已载入。13002/18002 隔离验收服务已停止，临时 TypeScript 构建路径已恢复。3001 本轮检查未在运行，未额外启动；已有便携 ZIP 未更新。

## 来源

MobileSAM：[作者项目](https://github.com/ChaoningZhang/MobileSAM)、[ONNX 导出项目](https://github.com/vietanhdev/samexporter)、[模型发布者](https://huggingface.co/vietanhdev/segment-anything-onnx-models)。模型包约 35 MiB，固定 SHA256 为 `41aff2660b7531becfee21fb257c49933ddc892c554507bdb775bf504d443942`，已有文件不覆盖。Codex 参见 [官方非交互模式](https://learn.chatgpt.com/docs/non-interactive-mode)。
