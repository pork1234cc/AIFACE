# 工作台 API 规划

更新日期：2026-09-21。阶段 5 已实现单张交付、自动更新与版本切换、单图下载、完成和关闭；供应商原始接口见 `../image2.md`。

## 1. 通用约定

- 路径前缀 `/api`；下表均为本地工作台接口，不直接暴露供应商密钥。
- JSON 使用 UTF-8，时间返回含时区的 ISO 8601 字符串。
- 创建资源返回 201，异步操作返回 202；读取和更新返回 200。
- 错误统一返回 `error.code`、`error.message`、可选 `error.details` 和 `request_id`。
- 未找到 404，状态冲突或幂等冲突 409，文件过大 413，文件类型不支持 415，参数错误 422。
- 列表支持 page、page_size，建议默认 20、上限 100。
- 应用层上传限制暂定 JPEG、PNG、WebP，单张不超过 20 MiB、解码后不超过 4000 万像素，实施联调时依据供应商限制收紧，前后端一致；不能仅凭扩展名判断真实格式。
- 每单素材最多 4 张；首次生成和修改均固定 1 张，成功自动成为唯一当前交付图。数量由后端决定，不接受前端任意覆盖。
- 修改轮次仅记录，不设硬上限；所有修改均手动发起。

## 2. 订单接口

下表接口均已实现。complete 和 close 无请求正文；同一终态重放返回成功，另一终态返回 409。

| 方法与路径 | 请求与行为 |
| --- | --- |
| POST /orders | customer_name、note；创建固定风格的草稿订单 |
| GET /orders | 分页，可按状态和客户备注名/订单号筛选 |
| GET /orders/{id} | 基本信息、素材、当前参数和 readiness；任务、交付和统计使用独立端点 |
| PATCH /orders/{id} | 更新 customer_name、note，不允许直接写状态 |
| PATCH /orders/{id}/params | 设置发型来源图片 ID、眼镜保留、服装模式及来源、额外要求 |
| POST /orders/{id}/ready | 校验素材及参数，进入 ready |
| POST /orders/{id}/request-revision | 人工标记待修改，需已有可用结果 |
| POST /orders/{id}/complete | 恰有一张有效当前交付图、文件完整且无未结束任务时完成 |
| POST /orders/{id}/close | 无未结束任务时关闭，不删除数据 |

完成或关闭后的订单只读，首版不提供重新打开入口。修改会影响生成条件的素材和参数时重新校验 ready/draft；历史任务快照不变。

### 阶段 2 具体请求和响应

`customer_name` 去除两端空白后长度 1～100，`note` 最多 2000 字符，未知字段和显式 null 被拒绝。PATCH 基本信息只修改显式提供字段。订单列表返回 `{items, total, page, page_size}`，`q` 为客户备注名/编号的字面子串搜索（不把 `%`、`_` 当通配符），按创建时间倒序分页。

详情包含基本字段、`params`、`assets` 和 `readiness: {ready, errors}`。任务摘要、当前交付和修改统计分别由 batches、finals、generation-stats 端点返回。图片响应包含 `content_url`，不暴露本机路径或 Base64。时间为 UTC ISO 8601 字符串。

阶段 3 任务摘要独立通过 `GET /orders/{id}/batches` 获取，订单详情仍沿用上述结构；assets 现在也包含 generated 图片。该接口分页返回 `{items, total, page, page_size}`，摘要字段为 batch_id、operation、status、target_count、created_at，按时间倒序。

`PATCH /orders/{id}/params` 合并显式提供字段后严格校验：

```json
{
  "hair_source_asset_id": "当前主照片或辅助照片ID",
  "glasses_keep": true,
  "clothes_mode": "reference",
  "clothes_source_asset_id": "当前参考图ID",
  "background": "white",
  "aspect_ratio": "1:1",
  "extra_requirement": "头发蓬松一点"
}
```

- 发型来源可暂存 null，但生成预检要求选择当前主照片或辅助照片；参考图不能作为发型来源。
- 服装模式为 `person`、`reference`、`simplified`。前两者分别要求当前本人照片、参考图 ID；简化模式要求来源为 null。初始默认简化服装、保留眼镜，发型来源待选。
- `glasses_keep` 只接受布尔值；背景和画幅只能为 `white` 和 `1:1`；额外要求最多 2000 字符。
- 素材移出或角色变化令来源失效时清空图片 ID，保留服装模式，提示重新选择，不擅自改变商家要求。恢复图片不自动恢复来源。
- 当前素材与参数有效时自动进入 ready，否则进入 draft；`POST /ready` 显式复验并保存，失败 422。该阶段不产生模型调用。

`POST /orders/{id}/prompt-preview` 接受与未来 generate 相同的 `inputs` 有序清单，只做预检，返回 `{inputs, params, style, prompt, target_count: 1}`。所有来源必须包含在该清单中，角色须与当前素材一致，图片不能重复。提示词用“图片 1、图片 2”等实际顺序引用；每个子任务的提示词只要求一张独立头像。此接口不建任务、不保存历史快照、不收费；阶段 3 提交时必须在写事务内重新校验。

## 3. 素材和结果

| 方法与路径 | 请求与行为 |
| --- | --- |
| POST /orders/{id}/images | multipart 文件和 role；限本人主照片、辅助照片或参考图 |
| PATCH /orders/{id}/images/{image_id}/role | 调整输入角色；切换主照片需原子更新旧主照片 |
| PATCH /orders/{id}/images/{image_id}/active | 用 active 布尔值移出或恢复当前输入集合，不删除文件；恢复时重新校验数量及角色 |
| GET /images/{image_id}/content | 返回受控图片内容 |
| PATCH /images/{image_id}/review | 对生成结果设置 unreviewed、selected、discarded |

每单最多一张主照片和一张参考图，总输入不超过 4 张。候选图和修改结果不计入订单上传素材额度，但发送给模型时仍计入单次 4 张额度。

阶段 2 上传字段名为 `file`、`role`，成功返回单张素材信息。上传另一张主照片/参考图返回 409；切换已有素材为主照片时，旧主照片在同一事务内降为辅助照片。角色/active 更新返回完整订单详情。恢复素材不会自动替换现有主照片或参考图，冲突时返回 409，可先调整被移出素材的角色。

图片按真实解码格式识别，不信任扩展名或 MIME 声明；拒绝损坏文件、SVG/GIF、动画和多帧图。使用 UUID 文件名、独占临时写入和原子重命名；原名称仅作显示。受控内容接口校验文件位于所属订单目录，设置准确 MIME、`nosniff` 和私有缓存策略。文件缺失返回 404。Next.js 转发缓冲配置为 22 MiB，包含 20 MiB 图片及 multipart 开销。

生成请求仅允许引用同订单图片和系统风格配置中明确可用的示例，不接受任意本机路径或前端传入的任意远程 URL。

已选为最终图的结果作废前，需先撤销最终选择。首版不实现物理删除；素材上传错误时先移出当前集合，再上传替代图片，不覆盖旧文件。移出会清空受影响的当前来源参数并重新校验就绪条件，历史生成记录不受影响。

## 4. 生成与修改

### 首次生成交付图

`POST /orders/{id}/generate`

请求头带 `Idempotency-Key`。请求体使用明确的有序图片清单，角色与订单素材对应；以下仅为结构示例：

```json
{
  "inputs": [
    { "asset_id": "main-photo-id", "role": "person_main" },
    { "asset_id": "aux-photo-id", "role": "person_aux" }
  ]
}
```

后端校验主照片、来源图片是否在实际输入中、总数上限及订单状态。风格和控制项读取当前订单并保存快照，创建一个结果位置（slot_index=0），不在本地 HTTP 请求中等待出图。

```json
{
  "batch_id": "batch-id",
  "operation": "initial",
  "target_count": 1,
  "status": "pending"
}
```

### 修改

`POST /orders/{id}/revise`

同样要求 `Idempotency-Key`：

```json
{
  "base_asset_id": "generated-image-id",
  "instruction": "保留整体风格，去掉眼镜",
  "additional_inputs": [
    { "asset_id": "main-photo-id", "role": "person_main" }
  ]
}
```

基础图必须是同订单、已落盘且未作废的结果。修改指令去除空白后不能为空。基础图占 1 张，附加图片最多 3 张；不能重复传入同一图片。响应结构同首次生成，operation 为 revision、target_count 固定为 1。

阶段 4 已开放以上接口。instruction 最多 2000 字符；additional_inputs 默认空列表，只接受本单当前 input 素材及其真实角色，不自动附加原主照片、来源照片或风格示例。基础图不依赖当前初稿 readiness，单独一张基础图即可修改。提交在同一写事务复验文件摘要、归属、成功状态、作废标记和单单一组约束。相同键重放优先于当前状态检查。

`PATCH /images/{image_id}/review` 正文为 `{"review_status":"selected"}`，可选 unreviewed、selected、discarded；返回更新后的单张资产，拒绝输入素材和终态订单。作废和恢复只改审阅标记，保留图片与历史任务，不改变已提交修改的输入快照。审阅标记保留兼容旧记录；主页面使用当前交付及版本切换。当前交付图不能作废，须先切换或撤销，直接作废返回 409 current_delivery。

`GET /orders/{id}/generation-stats` 返回 revision_count（修改组数）、successful_revision_count（成功修改组数）、generation_attempt_count（全单本地尝试记录数）、submitted_attempt_count（全单已进入供应商提交阶段的尝试数）。最后一项按 submitted_at 计数，不能作为严格 HTTP 到达次数或计费次数；提交前进程中断、外部探测均不能据此核算账单。补生成不增加 revision_count，无轮次硬上限。

`POST /orders/{id}/request-revision` 无正文，要求可编辑、无未结束任务且已有未作废成功结果，返回订单基本字段并置 revision_requested。直接 revise 不要求事先标记待修改。

修改以选中结果图及明确附加图片为本次输入，继承基础结果对应的风格版本，保存修改指令。原控制项作为来源记录，不自动重复施加会与本次修改冲突的要求；例如原来保留眼镜，本次“去掉眼镜”优先。

### 幂等与并发

- 本地键按操作路由与订单作用域唯一，保存规范化显式请求摘要；创建时的订单配置另存快照。
- 相同键且相同请求返回原任务组；相同键但业务请求变化返回 409。
- 幂等查找先于当前订单状态校验；配置在首次受理后变化也不能让同一次网络重发再建任务。新配置生成必须使用新键。
- 前端一次点击生成一个键，网络重发沿用该键；用户明确发起新操作使用新键。
- 同一订单存在未结束任务组时，新操作返回 409。
- 供应商幂等键按单次尝试生成，同次请求不随网络重试随机更换。

## 5. 查询与失败处理

本节所有端点已实现。生成/补生成/人工核对均返回 202，响应为完整任务组：`{batch_id, order_id, operation, target_count, status, created_at, finished_at, tasks, outputs}`。tasks 包含每次尝试的本地 ID、slot_index（新任务为 0，旧双图任务可为 1）、attempt_no（从 1 开始）、status、provider_task_id、脱敏错误、failure_stage、下次查询和时间、可空费用字段；outputs 包含本地素材响应及 generation_task_id。不返回内部路径、原始下载地址和请求快照。

写操作必填 `Idempotency-Key`，8～128 个 ASCII 字母、数字、下划线或连字符。重试正文为 `{"slot_indices":[0]}`，仅接受不重复的整数位置，布尔值不视为整数。同键重放返回原任务组的当前状态，不承诺状态字段与最初响应逐字相同。

阶段 4 任务组详情额外返回 base_asset_id、revision_instruction、style_version 及仅含 asset_id/role 的有序 inputs。历史摘要增加 base_asset_id 和 revision_instruction。详情的基础图 role 为 base；不返回文件路径或完整提示词。审阅 PATCH 与 request-revision 为设置状态操作，无须生成幂等键。

人工核对正文包含 action、note（去除首尾空白后 5～1000 字）、可选 provider_task_id 和 acknowledge_possible_duplicate_charge（严格布尔，默认 false）。link_remote_task 在事务外查询远端编号并核对 model 和 type=edit，再在事务内复验当前状态及编号唯一性；商家仍须依据供应商后台确认该任务属于本次提交。confirm_not_accepted 结束旧尝试为 failed，再由补生成按钮发起新尝试。resubmit_with_risk 立即另开一次尝试，旧尝试为 superseded_unknown。

| 方法与路径 | 行为 |
| --- | --- |
| GET /orders/{id}/batches | 分页返回初稿与修改历史 |
| GET /batches/{batch_id} | 聚合状态、目标数量、各位置尝试、错误、可用输出 |
| GET /tasks/{task_id} | 查询单个本地任务，区别于远端 task_id |
| POST /batches/{batch_id}/retry | 指定明确失败的 slot_indices，创建新尝试；要求幂等键 |
| POST /tasks/{task_id}/reconcile | 处理提交结果不明；要求幂等键、action 和核对说明 |

重试保持原任务组快照和目标数量；修改失败补生成不增加业务修改轮次。成功位置、执行中位置、submission_unknown 位置不能通过普通 retry 再次提交。

下载或本地持久化阶段失败时，retry 恢复原任务的下载/落盘，不重新请求模型；仅远端明确失败等需要重新生成的情况建立新尝试。

查询响应不得包含密钥、完整图片 Base64 或原始供应商鉴权响应。图片通过本地 asset_id 访问。

提交结果不明时返回 needs_attention 及可理解的提示。reconcile 的 action 限制为：link_remote_task（提交远端 ID，由后端查询核对后恢复）、confirm_not_accepted（记录未受理依据后允许新尝试）、resubmit_with_risk（商家明确接受潜在重复计费后新建尝试）。最后一种必须带 acknowledge_possible_duplicate_charge=true，旧尝试记为 superseded_unknown，保留未知费用。不得将普通超时解释为已确认未受理，也不能提供无说明的“自动修复”按钮。

## 6. 当前交付图与版本

| 方法与路径 | 行为 |
| --- | --- |
| GET /orders/{id}/finals | 返回 order_id、order_status、has_open_tasks、items、versions、history |
| PUT /orders/{id}/finals | 正文 asset_ids 最多 1 个；切换当前交付图，[] 明确撤销；返回同 GET |
| GET /orders/{id}/delivery | 下载当前单张原图；无当前图 409，文件缺失 404 |

新单图任务成功保存资产时，在同一事务内自动更新当前交付；修改失败保留原图。旧双图任务不自动挑选，商家可在版本历史明确选择。切换要求同单、成功、未作废、文件完整；相同当前图重复设置不新增历史。

items 包含 delivery_id、asset_id、selected_at、last_exported_at；versions 是成功结果的资产数组，含审阅标记；history 另含 revoked_at，保留自动替换与手动切回记录。每单最多一条未撤销记录。生成中、待核对及终态禁止切换。

下载返回准确图片 MIME、attachment 文件名（清理后的订单编号与图片短 ID）、private no-store 和 nosniff，不制作 ZIP，不包含客户名。先读取文件并校验摘要，再在短写事务复验选择记录未变化；变化返回 409，避免把旧版本记为本次导出。last_exported_at 只表示响应文件已准备，不证明客户已收到。

下载不自动完成订单；终态仍可查看和下载。完成要求当前图及文件有效，关闭不要求有图；两者均拒绝 pending/running/needs_attention 任务。同终态重复请求幂等，终态不提供重新打开、修改或版本切换。

## 7. 风格接口

- `GET /styles`：首版返回一个启用风格及封面信息。
- `GET /styles/{id}`：返回名称、版本、允许控制项、固定背景和比例、验收清单。
- 首版不提供风格编辑接口；风格配置由本地文件管理。

## 8. 已实现的系统接口

`GET /api/health` 检查数据库迁移版本是否达到当前 head；不调用模型，不要求模型密钥。成功返回 200：

```json
{"status": "ok", "database": "ready", "version": "0.1.0"}
```

数据库连接异常、未迁移或版本落后返回 503，`error.code` 为 `database_not_ready`，提示检查连接并执行迁移。错误包含 `request_id`，所有响应包含 `X-Request-ID`，不返回本机数据库路径或配置密钥。未知路由返回 404 `not_found`，请求校验失败返回 422 `validation_error`，未处理异常返回 500 `internal_error`；错误消息脱敏，不回显请求原文。

交互文档：`/api/docs`；OpenAPI：`/api/openapi.json`。

## 9. 变更记录

- 2026-09-21：按用户修正规则实现每次 1 张、成功自动交付、旧版切回、单图下载及独立完成/关闭；本条覆盖历史两图和多图交付规划。

- 2026-09-20：阶段 3 开放生成、任务查询、补生成和核对；同事务预检与文件摘要校验、持久化幂等和单个未结束任务组约束。真实供应商同键不同正文也返回原任务，故本地仍严格拒绝摘要冲突；有效期尚未知。

- 2026-09-20：完成阶段 2 订单、素材、风格和提示词预检接口，明确参数字段、来源失效处理、并发额度、返回结构和暂未开放的生成/交付端点。
- 2026-09-20：实现健康检查、关联 ID 和统一错误响应；原有业务接口仍待实施。
- 2026-09-20：创建本地 API 契约；落实输入 4 张、初稿 2 张、修改 1 张、轮次无硬上限，补齐异步状态、最终选择和交付接口。
