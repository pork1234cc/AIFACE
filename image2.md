# GPT Image 2.5 Sunburst API 接口文档

模型名称：`gpt-image-2.5-sunburst`
模型说明：最新图像生成与编辑模型 精细版，支持多尺寸输出，适合产出设计图草稿。

API Base URL：`https://ai.apii.cn`

## 鉴权

所有请求均需携带请求头：

```
Authorization: Bearer 你的APIKey
Content-Type: application/json
```

## 接口

- 文生图：`POST /v1/images/generations`
- 参考图编辑：`POST /v1/images/edits`
- 查询异步任务：`GET /v1/tasks/{task_id}`

## 请求参数

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| model | string | 是 | 模型名称，填写 gpt-image-2.5-sunburst |
| prompt | string | 是 | 图像内容描述 |
| aspect_ratio | string | 否 | 图片比例，例如 16:9、4:3、1:1 或 9:16，具体可参考下方比例尺寸表；参数生效后会覆盖 size 的参数值 |
| size | string | 否 | 详见下方尺寸表 |
| quality | string | 否 | 图像质量：auto、low、medium 或 high |
| output_format | string | 否 | 图片格式：png、jpeg 或 webp |
| response_format | string | 否 | 返回格式：url 或 b64_json |
| async | boolean | 否 | 是否异步执行；默认 false，传 true 时返回 task_id |
| mask | string | 否 | 局部重绘透明遮罩图，支持 Base64、Data URL 或公网图片 URL，需与参考图尺寸一致 |

图片编辑时传入 `images` 作为参考图数组，推荐使用公网图片 URL。局部重绘时额外传入 `mask`，遮罩支持 Base64、Data URL 或公网图片 URL，尺寸需与参考图一致。

## 比例与尺寸

填写有效的 `aspect_ratio` 后会覆盖 `size`。

| aspect_ratio | 对应 size |
| --- | --- |
| 16:9 | 2560x1440 |
| 21:9 | 2912x1248 |
| 4:3 | 2176x1632 |
| 3:2 | 2304x1536 |
| 5:4 | 2080x1664 |
| 1:1 | 1920x1920 |
| 4:5 | 1664x2080 |
| 2:3 | 1536x2304 |
| 3:4 | 1632x2176 |
| 9:16 | 1440x2560 |
| 9:21 | 1248x2912 |

自定义比例使用正整数 `n:m` 格式，长边与短边比例不得超过 3:1。宽高按 16px 的倍数计算，单边不超过 3840px，超出会等比缩小；总像素不超过 3686400。

## 文生图 cURL 示例

```bash
curl https://ai.apii.cn/v1/images/generations \
  -H "Authorization: Bearer 你的APIKey" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-image-2.5-sunburst",
    "prompt": "一张具有电影光影的高端香水产品海报",
    "aspect_ratio": "9:16",
    "quality": "high",
    "output_format": "png",
    "response_format": "url"
  }'
```

## 参考图编辑 cURL 示例（图片 URL）

```bash
curl https://ai.apii.cn/v1/images/edits \
  -H "Authorization: Bearer 你的APIKey" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-image-2.5-sunburst",
    "prompt": "将商品放入背景场景，并保持标签文字清晰",
    "images": ["https://tucdn.wpon.cn/2026/06/11/e2965f490445a-1781148062.png"],
    "aspect_ratio": "9:16",
    "quality": "high",
    "response_format": "url"
  }'
```

## 参考图编辑 cURL 示例（Base64）

```bash
curl https://ai.apii.cn/v1/images/edits \
  -H "Authorization: Bearer 你的APIKey" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-image-2.5-sunburst",
    "prompt": "将商品放入背景场景，并保持标签文字清晰",
    "images": ["图片的Base64字符串"],
    "aspect_ratio": "9:16",
    "quality": "high",
    "response_format": "url"
  }'
```

## 局部重绘 cURL 示例（mask）

```bash
curl https://ai.apii.cn/v1/images/edits \
  -H "Authorization: Bearer 你的APIKey" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-image-2.5-sunburst",
    "prompt": "只重绘遮罩透明区域，其他区域保持不变",
    "images": ["https://example.com/input.png"],
    "mask": "https://example.com/mask.png",
    "aspect_ratio": "1:1",
    "quality": "high",
    "response_format": "url"
  }'
```

## JavaScript 示例

```javascript
const response = await fetch("https://ai.apii.cn/v1/images/generations", {
  method: "POST",
  headers: {
    "Authorization": "Bearer 你的APIKey",
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    model: "gpt-image-2.5-sunburst",
    prompt: "一张具有电影光影的高端香水产品海报",
    aspect_ratio: "9:16",
    quality: "high",
    response_format: "url",
  }),
});

const result = await response.json();
console.log(result.data[0].url);
```

## Python 示例

```python
import requests

response = requests.post(
    "https://ai.apii.cn/v1/images/generations",
    headers={"Authorization": "Bearer 你的APIKey"},
    json={
        "model": "gpt-image-2.5-sunburst",
        "prompt": "一张具有电影光影的高端香水产品海报",
        "aspect_ratio": "9:16",
        "quality": "high",
        "response_format": "url",
    },
)

result = response.json()
print(result["data"][0]["url"])
```

## URL 返回结构

```json
{
  "created": 1782105234,
  "data": [
    {
      "url": "https://example.com/generated-image.png"
    }
  ]
}
```

## Base64 返回结构

```json
{
  "created": 1782105449,
  "data": [
    {
      "b64_json": "图片的Base64字符串"
    }
  ]
}
```

## 异步任务

在原文生图或编辑接口中增加 `"async": true` 后，请求会立即返回 `task_id`。不传或传 `false` 时仍按同步方式返回图片结果。

### 创建文生图任务

```bash
curl https://ai.apii.cn/v1/images/generations \
  -H "Authorization: Bearer 你的APIKey" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: order-20260914-001" \
  -d '{
    "model": "gpt-image-2.5-sunburst",
    "prompt": "一张具有电影光影的高端香水产品海报",
    "aspect_ratio": "9:16",
    "quality": "high",
    "output_format": "png",
    "response_format": "url",
    "async": true
  }'
```

立即返回：

```json
{
  "task_id": "7b4f0f34-0a73-4c70-9f0f-5c4d04b2f818",
  "status": "queued"
}
```

### 创建编辑任务

```bash
curl https://ai.apii.cn/v1/images/edits \
  -H "Authorization: Bearer 你的APIKey" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: order-20260914-002" \
  -d '{
    "model": "gpt-image-2.5-sunburst",
    "prompt": "将商品自然放入背景场景，并保持标签文字清晰",
    "images": ["https://tucdn.wpon.cn/2026/06/11/e2965f490445a-1781148062.png"],
    "aspect_ratio": "1:1",
    "quality": "high",
    "response_format": "url",
    "async": true
  }'
```

立即返回：

```json
{
  "task_id": "7b4f0f34-0a73-4c70-9f0f-5c4d04b2f818",
  "status": "queued"
}
```

### 查询任务

```bash
curl https://ai.apii.cn/v1/tasks/任务ID \
  -H "Authorization: Bearer 你的APIKey"
```

排队中：

```json
{
  "task_id": "7b4f0f34-0a73-4c70-9f0f-5c4d04b2f818",
  "status": "queued",
  "type": "generation",
  "model": "gpt-image-2.5-sunburst",
  "error": null,
  "created_at": "2026-09-14 10:00:00",
  "updated_at": "2026-09-14 10:00:00"
}
```

成功结果（文生图）：

```json
{
  "task_id": "7b4f0f34-0a73-4c70-9f0f-5c4d04b2f818",
  "status": "succeeded",
  "type": "generation",
  "model": "gpt-image-2.5-sunburst",
  "result": {
    "created": 1782105234,
    "data": [{ "url": "https://example.com/generated-image.png" }]
  },
  "error": null,
  "created_at": "2026-09-14 10:00:00",
  "updated_at": "2026-09-14 10:01:12"
}
```

成功结果（图片编辑）：

```json
{
  "task_id": "7b4f0f34-0a73-4c70-9f0f-5c4d04b2f818",
  "status": "succeeded",
  "type": "edit",
  "model": "gpt-image-2.5-sunburst",
  "result": {
    "created": 1782105234,
    "data": [{ "url": "https://example.com/generated-image.png" }]
  },
  "error": null,
  "created_at": "2026-09-14 10:00:00",
  "updated_at": "2026-09-14 10:01:12"
}
```

失败结果：

```json
{
  "task_id": "7b4f0f34-0a73-4c70-9f0f-5c4d04b2f818",
  "status": "failed",
  "type": "generation",
  "model": "gpt-image-2.5-sunburst",
  "error": {
    "code": "upstream_error",
    "message": "图像生成失败，请调整提示词后重试"
  },
  "created_at": "2026-09-14 10:00:00",
  "updated_at": "2026-09-14 10:01:12"
}
```