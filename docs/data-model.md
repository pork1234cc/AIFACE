# 统一创作数据模型

更新：2026-09-21。新流程不兼容旧订单，旧表与文件保留，当前业务只访问 `v2_*` 表。

## 存储

默认库 `storage/unified/database/aiface.sqlite3`，默认图片根 `storage/unified`。SQLite 启用外键、WAL、5 秒锁等待；写事务使用 BEGIN IMMEDIATE。迁移 0006 创建新表；0009 移除四图数量触发器；0010 调整订单状态约束并转换已有订单状态，保留任务和资产外键。

## 表与关系

| 表 | 内容与约束 |
| --- | --- |
| v2_orders | UUID、订单编号、客户备注、状态、params_json、时间；params_json 为 schema_version=2 统一配置 |
| v2_assets | input/generated、main/material 角色、活动标记、文件摘要和真实尺寸；每单至多一张活动 main，material 不设固定数量上限；生成资产唯一关联 generation_task_id |
| v2_generation_batches | initial/revision、target_count=1、base_asset_id、幂等键及摘要、有序输入、完整配置、风格快照及最终提示词；每单最多一个 pending/running/needs_attention 任务组 |
| v2_generation_tasks | slot_index=0、attempt_no>=1、远端编号、供应商请求快照、状态、错误阶段、查询时间、可空费用；远端编号及供应商幂等键唯一 |
| v2_generation_actions | retry/reconcile 的 scope、幂等键、摘要和任务组关联 |
| v2_order_deliveries | 当前选择与撤销历史；每单最多一条 revoked_at 为空；下载时间独立记录 |
| v2_custom_styles | custom_ 加 32 位十六进制编号、名称（60 字）、说明（200 字）、提示词（4000 字）、整数版本、创建及更新时间；迁移 0007 新增 |
| v2_style_preview_tasks | 迁移 0008 新增；风格编号外键、风格版本、幂等键、完整模型请求、底图摘要、状态、远端编号、下载地址、输出路径、错误、下次轮询、核对说明 |

主照片由上传角色明确指定，本次底图通过配置 base_asset_id 明确选择；继续修改时它必须等于当前交付资产。初始任务也保存 base_asset_id，所有结果都能追溯到实际底图。切回旧版不产生新图片或模型调用。

## 配置与快照

配置字段：schema_version=2、base_asset_id、style_id（q_crayon_001、自定义风格编号或 null）、changes、extra_requirement、aspect_ratio、output_format（png/jpeg/webp，默认 png）。订单模型请求的模型、quality 和接口地址从全局模型设置读取，并在每次任务创建时写入请求快照；quality 默认 high。

每个 changes 项保存 target_description、change_type、source_asset_ids、instruction、preserve_instruction。一个素材可用于多个修改项，同一项可引用多个素材；模型输入按首次引用顺序去重，素材数量不设固定上限。结构化项为空合法，文字修改可不引用素材。

当前参数可编辑；任务快照不随当前参数或风格文件更新而改变。风格 q_crayon_001 2.0.0 只控制表现；null 表示保持底图风格，快照版本为 original。失效素材引用不静默清除，历史快照始终保留。

自定义风格与订单使用同一数据库，按环境隔离，不写回内置风格 JSON。更新要求 expected_version 与库内版本相符；BEGIN IMMEDIATE 保护版本核对和递增，避免并发丢失修改。订单参数只引用风格编号；提交事务读取风格并固化完整快照。无删除接口，迁移不提供自动删表降级。

0008 为自定义风格增加 preview_task_id（最新任务）、cover_task_id（当前成功封面）、cover_version（封面对应版本），均可空。任务成功和封面指针在同一事务更新，失败不改封面；版本不同则 cover_stale=true。输出文件按风格/任务分目录，旧文件不删除。

示意图任务唯一约束为 (style_id, idempotency_key)，同键不同版本冲突；活动状态 pending/submitting/queued/running/downloading/submission_unknown 具有按 style_id 的部分唯一索引。终态 succeeded/failed；下载失败保留 URL，恢复时只重置为 downloading。URL 不进入公开响应，落盘成功后清除。进程在 submitting 中断时恢复为 submission_unknown，无远端编号不自动提交。

## 状态和事务

订单日常状态为 draft（待整理）、generating（生成中）、modifying（修改中）、review（待交付）、completed（已完成）；closed（已关闭）保留为特殊终态。素材齐备与否由 readiness 表达，配置保存不改变 draft。提交首次生成或修改任务时，同事务进入 generating 或 modifying；任务成功且图片、交付记录落盘后进入 review。首次失败回 draft，修改失败回 review，错误和尝试历史保存在任务表，已有交付图不变。重试同一任务快照时重新进入对应运行状态；提交结果不明保持运行状态并在任务信息中标记待核对，禁止自动重发。0010 将旧 ready 转 draft、旧 revision_requested 转 review，再按未结束任务的 operation 修正为运行状态。

任务组 pending/running/needs_attention/succeeded/failed。任务可为 pending/submitting/queued/running/downloading/succeeded/failed/submission_unknown/superseded_unknown。未结束及提交不明阻止新任务。旧双图部分成功不是新流程可创建的状态。

请求提交重新验证订单归属、底图版本、素材活动状态及文件摘要；快照与任务创建同事务完成。重试下载不重新生成，生成失败的新尝试保持原组配置和修改轮次。无已知计费依据时费用为 null。

## 变更记录

2026-09-21：0009_unlimited_materials 移除四图触发器；material_slots 保持前三个兼容位置，可按顺序增加更多编号。任务快照记录生图格式，默认 png，订单 quality 保持 high。

2026-09-21：订单支持永久删除。写事务内先检查未结束生成任务，解除生成组底图外键，再按交付、操作、素材、任务、任务组、订单顺序删除记录；提交后清理该订单图片目录。文件清理失败会在接口响应中标明，避免把数据库删除误报为失败。

2026-09-21：新增 0008_style_previews，封面任务与客户订单分开；只在用户点击生成时创建任务。

2026-09-21：新增迁移 0007_custom_styles 和自定义风格 CRUD 中的创建、读取、更新能力；内置风格保持只读，历史任务快照保持不变。

2026-09-21：以新库、新表和 schema_version=2 实施统一创作，取消旧角色、固定控制项及旧订单转换，保留新流程的恢复和版本历史。

2026-09-21：params_json 增加可空 material_slots 三项数组，索引0～2分别固定表示素材1～3，空位为 null；每个任务快照保存完整位置数组及实际有序输入。null 兼容历史 changes 协议。新界面保存空 changes 和统一文字要求；位置替换只停用旧输入，旧文件与快照不删除。底图指针与主图片角色独立，生成结果不替换原始主图片。
