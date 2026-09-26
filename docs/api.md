# 统一创作 API 契约

## 区域提示词（2026-09-26）

统一配置增加可选 `region_asset_id`（默认 null）和 `region_prompts`（默认 []，最多 20 项）。与 `material_slots` 同时使用，不改变既有 `changes` 协议。每项示例：

```json
{
  "id": "hair",
  "label": "头发",
  "target_description": "画面左侧人物的头发",
  "origin": "detected",
  "source_asset_ids": ["素材资产UUID"],
  "instruction": "仅参考发色",
  "preserve_instruction": "保留发型和长度"
}
```

id 为 1～64 位字母、数字、下划线或连字符，列表内唯一；label/target_description 为去空白后 1～100 字；origin 为 detected/manual；两个要求各最多 2000 字，可空。单区域最多引用 100 个素材资产。引用素材时必须填写修改用途。服务端核验素材属于本单、仍活动且存在于当前素材位置；同号替换不能自动继承旧引用。

非空 region_prompts 必须绑定当前 base_asset_id，否则拒绝保存/预览/生成并提示核对。完全空白的区域不产生修改指令；仅填写保留要求合法。非空区域要求以自然语言目标和真实图片输入序号组装，整体要求仍来自 extra_requirement。不向供应商发送识别蒙版，也不承诺像素锁定。新字段随任务快照固定，预览与生成共用同一组装函数。

`POST /orders/{order_id}/images/{asset_id}/regions`：无正文，只识别当前实际编辑底图。校验图片归属、活动主照片及文件完整性；不保存参数、不创建生成任务、不访问供应商。返回 `asset_id`、`regions`、`mask_url`（512×512 RGB PNG data URL）、width/height。每个候选含 id/label/target_description/origin/mask_value；红通道值为对应 mask_value，0 为未纳入候选。蒙版仅用于界面点击与高亮，不保存到草稿或任务。

错误：404 image_not_found；409 region_base_changed/region_model_busy；422 portrait_not_found；503 region_model_unavailable/region_inference_failed。识别失败仍支持手动添加区域。安装方式及已测边界见 [区域提示词设计](region-prompts.md)。

更新：2026-09-21。统一前缀 `/api`，仅支持新流程，不映射旧请求。错误为 `{error:{code,message,request_id}}`；不回显密钥、Base64 或内部文件路径。

## 统一配置

```json
{
  "schema_version": 2,
  "base_asset_id": "本单底图UUID",
  "style_id": "q_crayon_001",
  "changes": [
    {
      "target_description": "画面左侧人物的脸部",
      "change_type": "脸部身份",
      "source_asset_ids": ["素材UUID"],
      "instruction": "替换为素材中人物的身份特征",
      "preserve_instruction": "保留底图表情、朝向和身体姿态"
    }
  ],
  "extra_requirement": "保留背景及左右关系",
  "aspect_ratio": "3:4",
  "output_format": "png"
}
```

草稿 base_asset_id 可为 null，生成前必选；style_id 接受 q_crayon_001、custom_ 加 32 位小写十六进制编号，或 null（保持原图风格），保存参数和生成预览/提交均检查风格存在。changes 默认 []。每项目标与用途非空、最长 100 字，instruction 非空最长 2000 字，preserve_instruction 可空最长 2000 字；最多 20 个修改项。素材引用按 ID 去重，无三张数量上限，不静默截断。

aspect_ratio 仅接受 16:9、21:9、4:3、3:2、5:4、1:1、4:5、2:3、3:4、9:16、9:21，默认 1:1。output_format 仅接受 png、jpeg、webp，默认 png。订单生图的 quality 从全局模型设置读取，默认 high。尺寸由供应商比例表决定，无独立任意 size 或数量参数。额外字段被拒绝。

## 模型设置

`GET /model-settings` 返回 `{api_url,model,quality,has_api_key}`；绝不返回 API Key。`PUT /model-settings` 接收 `{api_url,model,quality,api_key?}`，仅支持现有 Apii 协议。接口 URL 必须是无路径、查询参数和账号的 HTTPS 根地址；质量限 `auto`、`low`、`medium`、`high`。`api_key` 为空时保留原密钥。保存更新后端 `.env` 并由 Worker 在后续任务读取；模型、质量和接口地址写入新任务快照，不重写已提交任务。

## 订单与素材

| 方法与路径 | 正文/行为 |
| --- | --- |
| POST /orders | customer_name（1～100 字）、note（可选），创建新订单 |
| GET /orders | q、status、page、page_size；返回 items/total/page/page_size，列表订单附带 last_batch_status（无任务时为 null） |
| GET /orders/{id} | 订单、params、assets、readiness |
| DELETE /orders/{id} | 永久删除订单及其素材、生成、交付记录和订单图片目录；有未结束任务时返回 409；成功返回 `{deleted:true,files_removed:true}`，文件清理失败时 `files_removed:false` |
| PATCH /orders/{id} | customer_name、note；终态不可写 |
| PATCH /orders/{id}/params | 统一配置字段；合并当前参数后校验；页面保存完整配置 |
| POST /orders/{id}/ready | 只校验当前已保存配置，缺底图/素材失效返回 422；不改变订单状态 |
| POST /orders/{id}/images | multipart：role=main/material 与 file；JPEG/PNG/WebP，20 MiB，4000 万像素，静态单帧 |
| POST /orders/{id}/image-slots/{slot} | slot=main 或素材正整数编号；素材新位置按顺序追加，替换或移出不重排已有编号 |
| POST /orders/{id}/image-slots/{slot}/clear | 移出指定位置图片并保留历史文件 |
| PATCH /orders/{id}/images/{asset_id}/role | `{role:"main"}` 或 material；设新主照片时原主照片降为 material |
| PATCH /orders/{id}/images/{asset_id}/active | `{active:false}` 移出、true 恢复；不删除文件；失效引用保留待修正 |
| GET /images/{asset_id}/content | 受控本地图片，校验归属路径 |

每单 main 最多一张，素材图数量不设固定上限；草稿可暂未选定底图。提交不接受跨订单、失效素材或主照片冒充素材引用。

订单状态筛选接受 draft（待整理）、generating（生成中）、modifying（修改中）、review（待交付）、completed（已完成）、closed（特殊终态：已关闭）。配置齐备仍保持 draft；订单列表按当前状态过滤，前端选中筛选项立即重新查询，并在页面可见时轮询更新。

## 预览与生成

`POST /orders/{id}/prompt-preview`、`POST /orders/{id}/generate`、`POST /orders/{id}/revise` 均接收 `{"config": <统一配置>}`。旧 inputs、instruction/additional_inputs 请求不接受。

预览只读，共用组装、底图当前版本及文件完整性校验，返回 inputs/params/style/prompt/target_count。首次生成底图必须为本单上传 main；继续修改必须为本单成功且未作废的当前交付图。修改项相同目标和用途出现不同要求时返回 conflicting_changes，要求合并澄清；不承诺解析全部自然语言矛盾。

生成/修改需 `Idempotency-Key`（8～128 个 ASCII 字母、数字、下划线、连字符），202 返回完整任务组。相同键相同正文重放返回当前组状态，不再调用模型；相同键不同正文返回 409 idempotency_conflict。配置正文参与摘要，事务内重新验证。每次仅一张。

首次提交在创建任务的同一事务将订单设为 generating，修改提交设为 modifying；成功保存结果后设为 review。明确失败分别回到 draft 或 review，订单列表以 last_batch_status=failed 提示，详情展示错误和重试入口。提交结果不明保持运行状态，以 last_batch_status=needs_attention 提示核对。重试使用原快照，下载或保存失败优先恢复原远端结果；失败尝试与错误历史保留。

发送到供应商前，服务端可能压缩图片的内联提交副本以缩小请求体；订单资产、配置快照和后续重试的输入来源不变。输入仍过大时任务以明确失败结束，日志提示减少素材或更换较小图片。供应商 HTTP 413 仍为明确拒绝，可在调整输入后重试。

任务组详情字段：batch_id/order_id/operation/base_asset_id/revision_instruction/style_version/config/prompt/inputs/target_count/status/created_at/finished_at/tasks/outputs。config 和 prompt 为对应版本快照，inputs 仅暴露 asset_id/role，不暴露内部路径。任务返回状态、远端编号、脱敏错误、错误阶段、尝试次数、时间及可空费用。

## 查询与恢复

| 方法与路径 | 行为 |
| --- | --- |
| GET /orders/{id}/batches | 分页摘要列表 |
| GET /batches/{batch_id} | 任务组、配置和完整提示词历史 |
| GET /tasks/{task_id} | 单任务状态 |
| GET /orders/{id}/generation-stats | 修改轮次、成功轮次、尝试与提交次数 |
| POST /batches/{batch_id}/retry | `{slot_indices:[0]}`，需幂等键；下载失败仅恢复原任务下载 |
| POST /tasks/{task_id}/reconcile | action、note、可选 provider_task_id、acknowledge_possible_duplicate_charge，需幂等键 |

reconcile action：link_remote_task（远端模型/类型核对后关联）、confirm_not_accepted（确认未受理后结束旧尝试）、resubmit_with_risk（明确接受重复费用风险另开尝试，必须 acknowledge_possible_duplicate_charge=true）。note 去空白后 5～1000 字。结果不明不自动重发。

审阅端点 PATCH /images/{id}/review 接受 review_status=unreviewed/selected/discarded；当前交付图不能作废。POST /orders/{id}/request-revision 只检查是否有可用结果，不改变状态；修改任务提交后才进入 modifying。

## 交付与终态

GET /orders/{id}/finals 返回 order_id/order_status/has_open_tasks/items/versions/history。PUT 同路径接收 asset_ids，最多一个；[] 撤销当前选择，文件和历史保留。同版本重复设置不重复记历史。

GET /orders/{id}/delivery 下载唯一当前原图；下载不完成订单。POST /orders/{id}/complete 要求有效当前交付；POST /orders/{id}/close 可关闭空单。两者均拒绝未结束任务，终态只读但允许下载。同终态重复请求幂等。

## 风格与健康

GET /styles 返回 items：先返回只读内置 q_crayon_001 2.0.0，再按创建时间和编号返回当前库的自定义风格。含 style_name/description/version/is_builtin/cover_image/initial_count/revision_count/prompt_template/qa_checklist。无真实封面时 cover_image=null。GET /styles/{id} 返回同样完整风格。原图风格选择为 null，不伪造风格包。

POST /styles 接受 `{style_name, description?, prompt}`，名称去空白后 1～60 字、说明最多 200 字、提示词去空白后 1～4000 字；严格拒绝未知字段。201 返回完整风格，自定义编号由服务端生成，is_builtin=false，version="1"。提示词保存至 prompt_template.system_style，其他字段为系统统一内容保留规则。

PUT /styles/{id} 接受上述完整编辑字段和 expected_version（正整数）。在写事务内核对版本，成功自动加一并返回完整风格；版本冲突返回 409 style_version_conflict，不覆盖他人修改；尝试改内置风格返回 403 builtin_style_readonly；不存在返回 404 style_not_found。没有删除接口。

订单保存风格引用，后续生成读取该风格当时的最新版；已提交任务固定完整风格及提示词快照，重试和同幂等键重放不读取新版本。风格维护不触发模型请求。

### 手动生成风格示意图

风格响应新增 cover_stale、preview。preview 可空，否则包含 task_id、request_key、status、error_message、can_resume_download。cover_image 成功后为受控同源 URL；未生成或首次失败为 null，再次失败保留旧链接。request_key 用于前端核对提交是否已受理，不在页面展示。

| 接口 | 行为 |
| --- | --- |
| POST /styles/{id}/previews | 正文 `{expected_version: 正整数}`，需 Idempotency-Key；202 返回完整风格。固定统一底图、1:1、单张，手动生成可能计费。 |
| GET /styles/{id}、GET /styles | 轮询 preview 状态与封面；不返回原始供应商 URL。 |
| GET /styles/{id}/previews/{task_id}/content | 校验任务归属和成功状态，返回本地图片；链接按任务不可变。 |
| POST /styles/{id}/previews/{task_id}/resume | 无正文；仅恢复最新任务已生成结果的下载，重复请求安全，不重新提交模型。 |
| POST /styles/{id}/previews/{task_id}/reconcile | 仅 submission_unknown 可核对，详见下段。 |

内置风格生成返回 403；不存在返回 404；风格版本冲突、正在执行/待核对或尚有可恢复下载结果均返回 409。同幂等键同版本重放不另建任务，不同版本返回 idempotency_conflict。终态明确失败可用新键重新生成。前端提交前保存键和版本，网络中断后复用，服务端活动任务约束覆盖跨标签页并发。

核对正文：action=link_remote_task 或 confirm_not_accepted、note（去空白后 5～1000 字）、provider_task_id（关联时必填）、confirmed_not_accepted（确认未受理时必须 true）。关联时查询并验证远端模型/类型和编号占用；成功改 queued 并恢复原任务查询。确认未受理改 failed，不自动生成，需要再点击重试。重复相同核对请求不会另发模型请求。

GET /health 核验数据库迁移 head，成功 `{status:"ok",database:"ready",version:"0.1.0"}`，不验证 Worker 或供应商在线。文档 /docs，OpenAPI /openapi.json。

## 固定素材位置（2026-09-21）

新界面配置使用 `material_slots: ["素材1资产UUID", null, "素材3资产UUID", "素材4资产UUID"]`（至少三项，可继续追加；允许 null，不允许重复），`changes: []`，用途统一放在 `extra_requirement`。空位不改变其他素材编号。模型输入是底图后依次附加非空位置，提示词显式映射“素材4 对应图片 4”等；明确引用未上传编号会返回 missing_material。未指明用途的素材不自动应用。

`material_slots: null` 或省略时兼容已有结构化配置和历史快照；新界面将旧修改项转换成文字再保存，旧任务快照不修改。固定位置与非空 changes 不能混用。

- `POST /orders/{id}/image-slots/{slot}`：slot 为 main 或正整数素材编号；multipart file，原位置资产停用并上传替换，返回 OrderDetail。新位置只能按顺序追加；界面的单个上传入口优先选最小空号。首次主图片自动设为底图；正在使用生成结果作底图时，替换主图片不改变该底图。
- `POST /orders/{id}/image-slots/{slot}/clear`：清空对应位置，其他编号不变，返回 OrderDetail；旧资产与文件保留。

固定位置操作拒绝已归档订单和存在未结束任务的订单。上传解码失败不改变原图；替换在同一数据库写事务完成。无需新增数据库迁移。
