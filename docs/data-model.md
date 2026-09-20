# 数据模型与状态设计

更新日期：2026-09-21。阶段 5 新增 0004_deliveries 与 0005_single_generation；当前交付唯一，新生成目标 1 张，兼容旧双图记录。

## 1. 数据原则

数据库默认位于 `storage/database/aiface.sqlite3`（可配置）。`0001_baseline` 保持不变，阶段 2 新迁移 `0002_orders_assets` 建立订单与素材表。连接启用外键、WAL 和 5 秒锁等待，迁移重复执行保留业务数据已验证。

- 输入最多 4 张；首次生成和修改目标均 1 张。
- 订单当前参数可调整，历史任务快照不可被当前参数覆盖。
- 图片文件、模型调用、人工选择分别记录，最终选定不会改变图片来源类型。
- ID 使用服务端生成的 UUID；订单另设唯一可读编号。
- 数据库时间统一使用 UTC，界面按 Asia/Shanghai 显示。
- 图片路径使用相对存储路径，通过受控接口访问，不返回任意本机绝对路径。
- 首版不提供物理删除接口；作废为可恢复标记，保留版本链。

## 2. 表结构

### orders：订单

| 字段 | 说明 |
| --- | --- |
| id / order_no | 主键、唯一订单编号 |
| customer_name / note | 客户备注名、订单备注 |
| source_channel | 来源，默认 xiaohongshu |
| style_id | 风格配置 ID，首版固定 q_crayon_001 |
| status | 业务状态，见状态流转 |
| params_json | 当前发型来源、眼镜保留、服装来源、白底及额外要求 |
| created_at / updated_at | 创建和更新时间 |

当前参数由后端严格校验。发型来源保存图片 ID；服装来源使用明确模式和可选图片 ID。首版不设置独立参数表，避免没有必要的一对一拆表。

已实现参数字段见 [API 具体契约](api.md)：hair_source_asset_id、glasses_keep、clothes_mode、clothes_source_asset_id、background、aspect_ratio、extra_requirement。订单主键为 UUID，编号为 `AF-UTC日期-完整UUID（去连字符）`，数据库再用唯一索引防冲突；时间保存为带 UTC 时区的 ISO 字符串。

### assets：图片资产

| 字段 | 说明 |
| --- | --- |
| id / order_id | 图片及所属订单 |
| kind | input、generated |
| input_role | 输入图片为 person_main、person_aux、reference；生成图片为空 |
| is_active_input | 是否属于当前输入集合；移出后保留文件和历史引用 |
| generation_task_id | 生成图片关联单次模型任务；输入图片为空 |
| relative_path / original_name | 存储相对路径、原始显示名称 |
| mime_type / byte_size / width / height | 实际文件信息 |
| sha256 | 完整性识别，不作为跨订单共享文件依据 |
| review_status | unreviewed、selected、discarded；用于生成图片 |
| sort_index / created_at | 展示顺序、创建时间 |

同一图片可作为多个修改任务的基础。首版以一个单图任务对应一张结果为预期，对 generation_task_id 建立适当唯一约束。

generation_task_id 现有外键及唯一约束；Worker 下载、校验并完成文件落盘后创建 generated 资产。迁移重建 assets 时保留已有素材、索引和两条数量触发器。资产创建后保留文件，移出只改 is_active_input。

### generation_batches：一次生成或修改操作

| 字段 | 说明 |
| --- | --- |
| id / order_id | 任务组及所属订单 |
| operation | initial、revision |
| base_asset_id | 修改基础图；initial 时为空 |
| revision_instruction | 修改要求；initial 时为空 |
| target_count | 新 initial 与 revision 固定 1；旧 initial=2 保留兼容 |
| status | 任务组聚合状态 |
| request_key / request_hash | 本地幂等标识及业务请求摘要 |
| input_snapshot_json | 按顺序保存发送图片的 ID、角色、校验信息 |
| params_snapshot_json | 控制项快照 |
| style_snapshot_json | 风格 ID、版本及本次使用的配置内容 |
| prompt_snapshot | 最终提示词 |
| created_at / finished_at | 创建及结束时间 |

不单独建立 revision_tasks 表：revision 类型的任务组已保存基础图、修改指令及结果关联，避免同一修改出现两套状态。

### generation_tasks：单次远端生成尝试

| 字段 | 说明 |
| --- | --- |
| id / batch_id | 子任务及所属任务组 |
| slot_index / attempt_no | 候选位置编号、该位置尝试次数 |
| status | 本地任务状态 |
| provider / model | 供应商标识、请求模型 |
| provider_task_id | 远端任务 ID，可空 |
| provider_idempotency_key | 本次远端请求使用的稳定键 |
| request_snapshot_json | 不含密钥的请求元数据，不复制 Base64 内容 |
| result_metadata_json | 必要结果元数据，敏感下载 URL 不进入普通日志 |
| error_code / error_message | 脱敏错误 |
| failure_stage | submit、remote、download、persist、protocol，用于决定恢复方式 |
| resolution_json | 结果不明时的核对动作、依据、时间及关联远端 ID |
| next_poll_at / claimed_at | 下一次查询时间、领取时间 |
| submitted_at / finished_at | 提交及结束时间 |
| cost_amount / cost_currency / cost_source | 费用及依据；未知均为空 |

新生成和修改只有一个位置；旧双图任务保留两个位置及恢复能力。失败补生成建立新的 attempt_no，保留旧尝试和费用记录；已有成功位置不能被普通重试替换。

阶段 3 实际位置编号从 0 开始、attempt_no 从 1 开始；(batch_id, slot_index, attempt_no) 唯一。provider_task_id 与 provider_idempotency_key 各自唯一。增加 poll_failures 用于查询退避。cost_amount 以可空十进制字符串预留，本阶段三个费用字段始终为空；不存在推测费用。

generation_actions 保存 retry/reconcile 的 scope、request_key、request_hash、batch_id 和创建时间，(scope, request_key) 唯一。任务组的 (order_id, operation, request_key) 唯一；部分唯一索引限制每单 pending/running/needs_attention 合计最多一组。快照输入包含有序 ID、角色、路径、MIME、尺寸、字节数和 SHA-256；没有密钥或 Base64。

Worker 进程对数据库旁的 `.worker.lock` 持有操作系统排他锁，进程退出自动释放；锁文件保留。首次领取在短写事务中变为 submitting，HTTP 调用不占写锁。重启将遗留 submitting（无远端编号）改为 submission_unknown；有编号继续查询。下载使用任务 ID 确定文件名，恢复时校验既有文件摘要，拒绝覆盖不同内容。

### order_deliveries：当前交付与切换历史

| 字段 | 说明 |
| --- | --- |
| id / order_id / asset_id | 交付选择及关联图片 |
| sort_index | 当前固定 0，非负 |
| selected_at / revoked_at | 选定时间、撤销时间 |
| last_exported_at | 最近导出时间，可空 |

每单仅一张当前交付图。部分唯一索引 uq_delivery_active 按 order_id 限制 revoked_at IS NULL 的记录。新单图任务成功时同事务撤销原选择并添加新选择；失败保留原图。切回历史版本新增选择记录，同当前图重复设置不新增记录。下载不自动代表客户已经收到，订单完成由商家明确标记。

## 3. 关系与约束

```text
orders
 ├─ assets
 ├─ generation_batches
 │   ├─ base_asset_id → 同订单 generated asset
 │   └─ generation_tasks → generated asset
 └─ order_deliveries → 同订单 generated asset
```

- SQLite 启用外键；不配置级联物理删除。
- 创建任务组时在事务中校验订单可操作、素材数量及所属关系，并保存快照和子任务。
- 同一订单首版只允许一个未结束的任务组；包含 submission_unknown 时也阻止新生成，避免重复付费。
- 上传及主照片切换在事务中检查最多 4 张、参考图最多一张、主照片唯一，避免并发绕过上限。
- 输入数量和角色约束针对 is_active_input=true 的当前集合。移出素材只改此标记；清空引用它的当前来源参数并重新校验就绪条件，历史快照保持不变。恢复素材同样校验额度和角色。
- 草稿阶段允许没有主照片；提交生成必须恰好一张。
- 已实现写事务使用 `BEGIN IMMEDIATE`，先获取写锁再读取素材额度/角色。当前主照片及参考图有部分唯一索引，INSERT/UPDATE 触发器兜底最多 4 张；不依赖进程内锁。文件解码在事务外进行，额度复验、文件落盘和数据库提交在事务内顺序完成。
- final 图片必须已完整落盘、属于该订单、未作废。
- 物理文件使用临时文件写入后原子重命名，再提交成功记录；异常中间文件留待明确的维护流程处理。
- 建议索引：订单状态/创建时间、资产 order_id、任务组 order_id/创建时间、任务 status/next_poll_at。

## 4. 状态设计

### 订单业务状态

| 状态 | 含义与进入条件 |
| --- | --- |
| draft | 待整理，新订单或素材不满足生成条件 |
| ready | 素材和参数检查通过，待生成 |
| review | 结果已可查看，待交付 |
| revision_requested | 商家标记待修改 |
| completed | 商家标记完成，恰有一张有效当前交付图且无未结束任务 |
| closed | 商家关闭，无未结束任务 |

生成中和生成失败通过任务组展示，不挤入订单业务状态。首次提交不自动标记 review，只有实际结果可用才进入 review。全失败时保留提交前业务状态。

completed、closed 首版作为只读终态，不新增生成；重新打开暂不实现。关闭不删除文件。上述状态行为属于实施设计，业务调整需同步 API 和验收文档。

### 子任务状态

`pending → submitting → queued / running → downloading → succeeded`

- `failed`：远端明确失败或已明确无法完成的本地处理。
- `submission_unknown`：提交结果不明，不能当作普通失败自动重试。
- `superseded_unknown`：经人工明确接受可能重复计费并另开尝试后，旧尝试保留为结果未知；保留潜在费用，不能记为零费用失败。
- 排队或生成状态仅按远端实际返回映射；未知状态保留原始值并报错，不猜测成功。
- 网络查询失败不会把远端任务直接判为 failed；保存错误并安排下次查询。

### 任务组聚合状态

- pending：尚未执行。
- running：存在执行中任务。
- succeeded：各目标位置均有一个成功结果，新生成/修改均 1 个，历史双图为 2 个。
- partial_failed：仅历史双图任务的一个位置成功，其余位置明确失败。
- failed：所有目标位置均明确失败。
- needs_attention：存在 submission_unknown，优先提示人工核对。

重试时按各位置最新尝试聚合，历史尝试保留。待处理、执行中和 needs_attention 均属于未结束状态。

下载或持久化失败优先恢复原任务，不创建新的模型尝试；只有明确需要重新调用模型时才增加 attempt_no。结果不明核对后关联已有远端任务则继续原任务；确认未受理可记录依据后结束该尝试并建立新尝试；明确接受重复计费风险后重发则保留旧记录为 superseded_unknown。

## 5. 轮次统计

修改请求形成一个 revision 任务组；失败任务的补生成不另计修改轮次。分别统计修改操作数、成功修改数、本地尝试数和已进入提交阶段的尝试数，避免用一个计数同时表示业务返工与费用。

阶段 4 已实现：基础生成任务必须 succeeded，结果未作废，归属相同订单；实际输入第 1 项固定为基础图，另可明确选最多 3 张当前素材。同事务检查真实文件摘要。继承基础任务组的 style_snapshot_json；params_snapshot_json 只保留来源记录，不再用于组装旧发型/眼镜/服装指令。修改提示词使用原风格渲染约束和本次指令，后续修改可继续以修改结果为基础，沿 base_asset_id → generation_task_id → batch_id 追溯。

统计端点使用聚合查询，返回修改组数、成功修改组数、全单尝试数及 submitted_at 非空的尝试数，不逐组查询。submitted_at 标记“已进入提交阶段”，不证明供应商收到请求或实际计费。没有设置/预留虚构的费用零值，也不把额外供应商探测算入本地任务数。

用户已确认：只记录修改轮次，由商家控制，不设置系统硬上限。每次修改由商家手动发起，不自动循环返工。

## 6. 变更记录

- 2026-09-21：新增交付记录与单图目标迁移。0005 重建任务组约束时仅在迁移连接临时关闭外键，保留所有旧记录并执行 foreign_key_check。默认库先在线备份到 storage/database/before-stage5-20260921-005105.sqlite3 再升级；原订单、资产、任务组、任务与幂等动作逐字段一致，不替旧双图订单自动选图。迁移重复执行、唯一约束与 Alembic check 通过。

- 2026-09-21：实现单图修改、明确附加素材、基础图版本链、审阅标记和轮次聚合；沿用 0003，无结构变化。模拟浏览器验证 4 输入生成 1 张修改图及审阅恢复。

- 2026-09-20：阶段 3 模型与独立迁移、任务快照、两个位置、幂等表和 Worker 完成。旧版含素材数据库迁移保留测试及 Alembic check 通过；默认库迁移前已做 SQLite 在线备份并保留原有 1 笔订单。

- 2026-09-20：完成订单、素材模型和独立业务迁移；实现 UTC 字符串时间、JSON 当前参数、软移出、部分唯一索引、素材数量触发器和 SQLite 串行写事务；后续任务/交付表尚未创建。
- 2026-09-20：阶段 1 建立 SQLite 和 Alembic 迁移基线；业务表设计未变，仍待实施。
- 2026-09-20：新增首版数据模型；明确初稿 2 张、修改 1 张，分离图片来源和最终选择，统一生成与修改记录。
