# comfyui-arksd

[English](README_EN.md) | 中文说明

用于 **火山方舟（Volcengine Ark）Seedance 2.x** 视频生成的 ComfyUI 节点。

通过异步 HTTP 直接调用方舟视频生成 API，支持把方舟**素材**（`asset://<id>`）
作为参考图、参考视频和参考音频 —— 这正是旧的即梦类节点所缺少的能力。

## 功能

- **Seedance 2.5**、**2.0**、**2.0 Fast**、**2.0 Mini** 各自独立的节点
- 参考素材支持**素材 ID**、公网 URL，或 ComfyUI 本地图片
- Seedance 2.5 的**样片模式**：先出一段便宜的 480p 预览，再生成 1080p 成片
- 阻塞（等待出片）与非阻塞（立即返回任务 ID）两种模式
- 任务列表节点：浏览、自动刷新、取消排队中的任务，且不经过 ComfyUI 执行队列
- 带缩略图的素材选择器，选之前能看清是哪张图

## 安装

```bash
cd ComfyUI/custom_nodes
git clone <this-repo> comfyui-arksd
pip install -r comfyui-arksd/requirements.txt
```

重启 ComfyUI。节点出现在 `api node/ArkSD` 分类下。

唯一依赖是 `httpx`，ComfyUI 已自带。

## 凭据配置

两个文件，都已被 git 忽略，都由对应的 `.example` 文件复制而来。凭据只从文件
读取 —— 没有用于填写凭据的输入框，因为输入框的值会被存进工作流 JSON。

### `api_keys.json` —— 用于视频生成

在方舟控制台获取 API Key：<https://ark.volcengine.com/region:cn-beijing/apikey>

```json
[
  { "customName": "Ark-Main", "apiKey": "your-ark-api-key" }
]
```

### `ak_sk.json` —— 用于素材库

素材接口属于管控面 API，只接受 Access Key / Secret Key 对，不接受 API Key。
在 <https://console.volcengine.com/iam/keymanage> 获取。

```json
[
  {
    "customName": "Ark-AK",
    "accessKey": "your-access-key",
    "secretKey": "your-secret-key",
    "region": "cn-beijing"
  }
]
```

只有使用 **ArkSD Asset** 节点时才需要 `ak_sk.json`。生成类节点仅凭
`api_keys.json` 即可工作。

## 节点一览

所有生成节点的 `duration` 默认都是 5 秒；填 `-1` 表示让模型自行决定，也可以
直接指定具体秒数。

每个生成节点都会输出 `VIDEO`、`seed`（整数）、`task_id`（字符串）和
`last_frame`（图像）。`last_frame` 仅在开启 `return_last_frame` 时才有值。
未开启时该输出会被**阻断**：连在它下游的节点会被跳过并给出说明，而不是拿着
空值崩溃。断开该连线，或开启 `return_last_frame`。

| 节点 | 作用 |
|---|---|
| **ArkSD Asset** | 从方舟素材库选择素材，输出 `asset://<id>` |
| **ArkSD Asset (Manual ID)** | 直接手填素材 ID，用于列表看不到的授权素材 |
| **ArkSD Seedance 2.5** | Seedance 2.5 生成，含样片模式 |
| **ArkSD Seedance 2.0** | Seedance 2.0 生成（支持 4k） |
| **ArkSD Seedance 2.0 Fast** | 更快更便宜，仅 480p/720p |
| **ArkSD Seedance 2.0 Mini** | 成本最低，仅 480p/720p |
| **ArkSD Draft to Video** | 把样片任务 ID 转成 1080p 成片 |
| **ArkSD Query Task** | 按任务 ID 查询并等待出片；输出视频、种子、状态和该任务 ID |
| **ArkSD Task List** | 浏览、自动刷新、取消任务（纯 UI） |
| **ArkSD LLM** | 调用方舟对话接口，返回文本，最多 5 张图 |
| **ArkSD Texts** | 把最多 10 段文本拼接成一段 |

## 文本生成

**ArkSD LLM** 调用方舟 OpenAI 兼容的 `/chat/completions` 接口。接口地址固定
为方舟，凭据取自 `api_keys.json`，因此没有 API 地址或 API Key 输入框，工作流
文件里也不会残留任何密钥。

`model` 字段默认为空。旁边的下拉框列出方舟模型目录（来自
`GET /api/v3/models`，按 domain 分组，已隐藏 `Shutdown` 与 `Retiring`
状态的模型）；选中即填入该字段，同时仍可手填任意模型 ID 或 `ep-` 开头的
接入点 ID。该目录是全平台目录，**不是**你账号已开通的模型：选了未开通的模型
会返回 `ModelNotOpen`，错误信息会提示你到方舟控制台开通。

输入项与参考节点保持一致：`system_prompt`、`prompt`、`temperature`、
`top_k`、`top_p`、`presence_penalty`、`frequency_penalty`、`max_tokens`、
`timeout`、最多 5 张可选图片，以及三项图片编码限制。`top_k` 仅在大于 0 时
发送。图片会转成 JPEG 并压缩，直到不超过 `image_max_kb`。

**ArkSD Texts** 把最多 10 段文本用可选分隔符拼接起来，适合把多段生成结果
拼成一段提示词。

```
ArkSD LLM ──text──> ArkSD Texts ──text──> ArkSD Seedance 2.5.prompt
```

## 参考素材

| 插槽 | 接受类型 | 说明 |
|---|---|---|
| `reference_image_N` | `IMAGE` 或 `STRING` | `LoadImage` 的输出会自动转 base64 |
| `reference_video_N` | `VIDEO` 或 `STRING` | `LoadVideo` 的输出按下方限额转成 base64；字符串则视为 `asset://<id>` 或公网 URL |
| `reference_audio_N` | `AUDIO` 或 `STRING` | `LoadAudio` 的输出按下方限额转成 WAV；字符串则视为 `asset://<id>` 或公网 URL |

三种插槽都同时接受 ComfyUI 的值和字符串。连接字符串时会原样使用：可以是
`asset://<id>`、公网 URL，或 `data:` URI。

### 本地视频与音频参考

本地素材可以直接从 **Load Video** 和 **Load Audio** 连入。只有同时满足两项
限制时才会以 base64 内联发送：

| 限制 | 视频 | 音频 |
|---|---|---|
| 体积 | 30 MB | 30 MB |
| 时长 | Seedance 2.0 / Fast / Mini：15 秒<br>Seedance 2.5：30 秒 | Seedance 2.0 / Fast / Mini：15 秒<br>Seedance 2.5：30 秒 |
| 编码 | 原文件 base64 | 16-bit PCM WAV，再 base64 |

超出任一限制都会在请求发出前被拒绝，错误信息里会写明真实限额。要用更长或更大
的素材，请上传到方舟素材库后传 `asset://` ID，或放到公网 URL。

30 MB 的上限是因为方舟限制整个请求体为 64 MB。

**不涉及格式转换，也不需要 ffmpeg。** ComfyUI 在节点拿到数据之前就已把各种
容器格式（mp4、mov、mp3、wav、flac、m4a）解码成内存中的值，因此不存在格式不
匹配的问题。音频之所以重新编码成 WAV，是因为方舟没有可以直接传递的内存表示；
WAV 不压缩，所以即使时长没超限，特别长的片段也可能先撞上体积上限。

各模型的参考素材数量上限：

| 模型 | 图片 | 视频 | 音频 |
|---|---|---|---|
| Seedance 2.5 | 30 | 10 | 10 |
| Seedance 2.0 / Fast / Mini | 9 | 3 | 3 |

### 本地图片会自动调整

方舟要求每张参考图不超过 30 MB，宽高比在 0.4–2.5 之间，单边在 300–6000
像素之间。`LoadImage` 的输出很容易超出这些范围，因此图片会被缩放并重新编码
直到合规，每次调整都会打日志：

```
[ArkSD] reference_image_0 resized 4096x4096 -> 2048x2048 (edge/ratio limit)
[ArkSD] reference_image_0 re-encoded as JPEG (size limit)
```

## 工作流示例

### 文生视频

```
ArkSD Seedance 2.5 ──VIDEO──> SaveVideo
```

### 图生视频

```
LoadImage ──IMAGE──> ArkSD Seedance 2.5.reference_image_0
ArkSD Seedance 2.5 ──VIDEO──> SaveVideo
```

### 使用素材（例如他人授权的真人人像）

```
ArkSD Asset ──asset──> ArkSD Seedance 2.5.reference_image_0
ArkSD Seedance 2.5 ──VIDEO──> SaveVideo
```

在提示词中按位置引用素材，例如 `image1`，不要直接写素材 ID。

### 该用哪个素材节点

| 你的情况 | 使用节点 |
|---|---|
| 素材属于你自己的账号 | **ArkSD Asset** —— 从列表选择，带缩略图 |
| 素材是别人授权给你的 | **ArkSD Asset (Manual ID)** —— 手填控制台里的素材 ID |

方舟的素材管理 API 只能看到你账号自己拥有的素材。方舟真人人像素材指南原文：

> Asset (Group) 管理 API 仅可查询、更新或删除用户所在账户内的素材组/素材，
> 其他账户授权使用的素材无法通过以上素材管理 API 进行查询、更新或删除操作。

视频生成 API 仍然接受这些 ID，所以 **ArkSD Asset (Manual ID)** 就是入口。
在方舟控制台的「我的 → 真人人像 → 授权给我的」中复制素材 ID 填入即可。该 ID
会被原样传为 `asset://<id>`，不做任何查询，因此不显示预览。

素材归属于方舟的**项目**。默认项目名为 `default`，但素材也可以放在命名项目
下。如果 **ArkSD Asset** 里看不到你的素材，请把 `project_name` 设为控制台里
显示的项目名。项目名填错时会静默返回空列表，不会报错。

`group_type` 选择器有三个取值：

| 取值 | 列出的内容 |
|---|---|
| `AIGC` | 你自己创建的虚拟人像素材 |
| `LivenessFace` | 真人人像素材，包含他人授权给你的 |
| `All` | 两者都包含 —— 节点会按类型各查一次再合并 |

方舟每次请求只接受一种 group type，所以 `All` 会产生两次 API 调用。

### 样片模式（Seedance 2.5）

Seedance 2.5 的 `draft` **默认开启**。开启期间节点界面上的 `resolution` 会
被锁定为 `480p`，因为方舟对样片只接受这一种分辨率。关闭它即可直接生成成片。

```
ArkSD Seedance 2.5（draft=true, resolution=480p）
    ├── VIDEO     -> 预览 480p 样片
    └── task_id   -> ArkSD Draft to Video -> VIDEO（1080p）-> SaveVideo
```

样片模式是两个独立计费的任务。样片任务 ID 有效期为 7 天。
`ArkSD Draft to Video` 会自动复用样片阶段的提示词、参考素材、时长、宽高比、
随机种子和音频设置；它只允许你重新指定 `output_format`、`watermark`、
`return_last_frame`、`priority` 和 `execution_expires_after`。

### 非阻塞提交

```
ArkSD Seedance 2.5（non_blocking=true）──task_id──>（保存起来）
ArkSD Query Task（task_id=...）──VIDEO──> SaveVideo
```

### 把种子写进文件名

`SaveVideo` 会在节点上内联预览并保存文件。要把种子写进文件名，把生成节点的
`seed` 输出经「转字符串」和「文本拼接」节点接到 `SaveVideo` 的
`filename_prefix` 即可。

## 素材列表缓存

素材列表会缓存 **5 分钟**。生成一个视频至少需要这么久，因此一次运行期间在方舟
控制台做的改动会在下一次运行时生效。勾选 **ArkSD Asset** 节点上的 `refresh`
可强制立即重新拉取。

## 修改凭据后需要重启

`customName` 下拉框是在启动时注册节点定义的那一刻生成的，这是 ComfyUI 的
限制。如果你在 `api_keys.json` 或 `ak_sk.json` 中新增或重命名了条目，需要重启
ComfyUI 才能看到。仅修改已有条目的密钥值则立即生效。

## 取消任务

方舟只允许取消仍处于**排队中**的任务。已经开始运行的任务无法取消。

- **生成节点正在等待时**，按 ComfyUI 的 **Cancel** 按钮。节点会取消远端的
  任务并停止等待。
- **对于其它任务**，使用 **ArkSD Task List** 节点上的 **Cancel** 按钮。它不
  经过执行队列，因此即使在 ComfyUI 队列繁忙时也能工作。

## 模型开通状态

没有 API 可以查询你的账号开通了哪些模型。如果你提交到未开通的模型，节点会
停止并给出写明模型名称的清晰错误。到方舟控制台（模型广场 → 对应 Seedance
模型 → 开通）开通后重试即可。

## 备注

- 任务 ID 和视频 URL 只保留有限时间。视频 URL 在 24 小时后失效，Seedance 2.5
  的视频 URL 有 100 次下载上限。
- 任务列表只显示最近 7 天的任务。
- Seedance 2.5 和 2.0 不接受直接上传含真人人脸的参考图或视频。请改用素材库中
  已授权的素材。

## 许可协议

MIT。见 [LICENSE](LICENSE)。
