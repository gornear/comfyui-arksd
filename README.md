# comfyui-arksd

English | [中文说明](README-ZH_CN.md)

ComfyUI nodes for **Volcengine Ark (火山方舟) Seedance 2.x** video generation.

Calls the Ark video generation API directly over async HTTP, with support for
Ark **assets** (`asset://<id>`) as reference images, videos, and audio — the
capability the older Jimeng-style nodes lack.

## Features

- Seedance **2.5**, **2.0**, **2.0 Fast**, and **2.0 Mini** as separate nodes
- Reference input by **asset id**, public URL, or a local ComfyUI image
- **Draft mode** for Seedance 2.5: a cheap 480p preview, then a 1080p final
- Blocking (wait for the video) and non-blocking (return the task id) modes
- A task list node that browses, auto-refreshes, and cancels queued tasks
  without going through the ComfyUI queue
- An asset picker with thumbnails, so you can see what you are selecting

## Installation

```bash
cd ComfyUI/custom_nodes
git clone <this-repo> comfyui-arksd
pip install -r comfyui-arksd/requirements.txt
```

Restart ComfyUI. The nodes appear under the `api node/ArkSD` category.

The only dependency is `httpx`, which ComfyUI already ships.

## Credentials

Two files, both git-ignored, both created by copying the matching `.example`
file. Credentials are read from files only — there are no credential input
widgets, because widget values are stored in the workflow JSON.

### `api_keys.json` — for video generation

Get an API key from the Ark console: <https://ark.volcengine.com/region:cn-beijing/apikey>

```json
[
  { "customName": "Ark-Main", "apiKey": "your-ark-api-key" }
]
```

### `ak_sk.json` — for the asset library

The asset API is a management-plane API and only accepts an Access Key /
Secret Key pair, not an API key. Get one from
<https://console.volcengine.com/iam/keymanage>.

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

You only need `ak_sk.json` if you want to use the **ArkSD Asset** node. The
generation nodes work with just `api_keys.json`.

## Nodes

Each generation node outputs `VIDEO`, `seed` (INT), `task_id` (STRING), and
`last_frame` (IMAGE). `last_frame` is only filled when `return_last_frame` is
on. When it is off, the `last_frame` output is **blocked**: any node connected
to it is skipped with an explanatory message instead of crashing on an empty
value. Disconnect it, or turn `return_last_frame` on.

| Node | What it does |
|---|---|
| **ArkSD Asset** | Pick an asset from your Ark library; outputs `asset://<id>` |
| **ArkSD Asset (Manual ID)** | Type an asset id directly; for authorized assets the list cannot show |
| **ArkSD Seedance 2.5** | Seedance 2.5 generation, including draft mode |
| **ArkSD Seedance 2.0** | Seedance 2.0 generation (supports 4k) |
| **ArkSD Seedance 2.0 Fast** | Cheaper and faster, 480p/720p |
| **ArkSD Seedance 2.0 Mini** | Lowest cost, 480p/720p |
| **ArkSD Draft to Video** | Turn a draft task id into the 1080p final |
| **ArkSD Query Task** | Fetch one task by id and wait for its video; outputs the video, seed, status, and the task id |
| **ArkSD Task List** | Browse, auto-refresh, and cancel tasks (UI only) |
| **ArkSD LLM** | Call Ark's chat completions endpoint; returns text, up to 5 images |
| **ArkSD Texts** | Concatenate up to 10 text inputs into one string |

## Text generation

**ArkSD LLM** calls Ark's OpenAI-compatible `/chat/completions` endpoint. The
endpoint is fixed to Ark and the credential is taken from `api_keys.json`, so
there is no api url or api key widget and no secret ends up in the workflow
file.

The `model` field starts empty. A dropdown next to it lists the Ark model
catalog (from `GET /api/v3/models`, grouped by domain, with `Shutdown` and
`Retiring` models hidden); picking one fills the field, and you can still type
any id or an `ep-` endpoint id by hand. The catalog is platform-wide, not the set of models your account
has opened: choosing one you have not opened makes the request fail with
`ModelNotOpen`, and the error tells you to open it in the Ark console.

Inputs mirror the reference node: `system_prompt`, `prompt`, `temperature`,
`top_k`, `top_p`, `presence_penalty`, `frequency_penalty`, `max_tokens`,
`timeout`, up to 5 optional images, and three image-encoding limits. `top_k` is
only sent when it is greater than 0. Images are converted to JPEG and shrunk
until they fit `image_max_kb`.

**ArkSD Texts** concatenates up to 10 text slots with an optional delimiter,
which is handy for building a prompt out of generated pieces.

```
ArkSD LLM ──text──> ArkSD Texts ──text──> ArkSD Seedance 2.5.prompt
```

## Reference inputs

| Slot | Accepts | Notes |
|---|---|---|
| `reference_image_N` | `IMAGE` or `STRING` | A `LoadImage` output is converted to base64 automatically |
| `reference_video_N` | `VIDEO` or `STRING` | A `LoadVideo` output is inlined as base64 within the limits below; a string is an `asset://<id>` or a public URL |
| `reference_audio_N` | `AUDIO` or `STRING` | A `LoadAudio` output is inlined as WAV within the limits below; a string is an `asset://<id>` or a public URL |

All three slots accept either a ComfyUI value or a string. When a string is
connected it is used as-is: an `asset://<id>`, a public URL, or a `data:` URI.

### Local video and audio references

Local media can be connected straight from **Load Video** and **Load Audio**.
It is inlined as base64 only when it passes both gates:

| Gate | Video | Audio |
|---|---|---|
| Size | 30 MB | 30 MB |
| Duration | Seedance 2.0 / Fast / Mini: 15 s<br>Seedance 2.5: 30 s | Seedance 2.0 / Fast / Mini: 15 s<br>Seedance 2.5: 30 s |
| Encoding | base64 of the original file | 16-bit PCM WAV, then base64 |

Anything over a limit is refused before the request is sent, with the real
limit named in the error. To use longer or larger footage, upload it to your
Ark asset library and pass the `asset://` id, or host it at a public URL.

The 30 MB cap exists because Ark limits the whole request body to 64 MB.

**No format conversion and no ffmpeg are involved.** ComfyUI decodes whatever
container you load (mp4, mov, mp3, wav, flac, m4a) into an in-memory value
before the node sees it, so there is no format mismatch to resolve. Audio is
re-encoded to WAV because Ark has no in-memory representation to pass through;
WAV is uncompressed, so a very long clip can reach the size cap even when it is
inside the duration cap.

Reference limits per model:

| Model | Images | Videos | Audio |
|---|---|---|---|
| Seedance 2.5 | 30 | 10 | 10 |
| Seedance 2.0 / Fast / Mini | 9 | 3 | 3 |

### Local images are adjusted automatically

Ark requires each reference image to be at most 30 MB, with an aspect ratio
between 0.4 and 2.5 and each edge between 300 and 6000 px. A `LoadImage`
output can easily exceed that, so images are scaled and re-encoded until they
fit, and every adjustment is logged:

```
[ArkSD] reference_image_0 resized 4096x4096 -> 2048x2048 (edge/ratio limit)
[ArkSD] reference_image_0 re-encoded as JPEG (size limit)
```

## Workflows

### Text to video

```
ArkSD Seedance 2.5 ──VIDEO──> SaveVideo
```

### Image to video

```
LoadImage ──IMAGE──> ArkSD Seedance 2.5.reference_image_0
ArkSD Seedance 2.5 ──VIDEO──> SaveVideo
```

### Using an asset (for example an authorized real-person portrait)

```
ArkSD Asset ──asset──> ArkSD Seedance 2.5.reference_image_0
ArkSD Seedance 2.5 ──VIDEO──> SaveVideo
```

In the prompt, refer to the asset by its position, for example `image1`, not by
its asset id.

### Which asset node to use

| Your situation | Node |
|---|---|
| The asset belongs to your own account | **ArkSD Asset** — browse the list, pick with a thumbnail |
| Another account authorized the asset to you | **ArkSD Asset (Manual ID)** — type the id from the Ark console |

Ark's asset management API can only see assets your own account owns. From the
Ark real-person asset guide:

> Asset (Group) management APIs can only query, update, or delete asset groups
> and assets inside the user's own account. Assets authorized by other accounts
> cannot be queried, updated, or deleted through these APIs.

The video generation API still accepts those ids, so **ArkSD Asset (Manual ID)**
is the way in. Copy the asset id from the Ark console under
"My → Real-person portrait → Authorized to me" and paste it there. It is passed
through as `asset://<id>` with no lookup, so no preview is shown.

Assets live inside an Ark **project**. The default project is called
`default`, but assets can live in a named project. If your assets do not show up
in **ArkSD Asset**, set `project_name` to the project shown in the Ark console.
A wrong project returns an empty list without an error.

The `group_type` selector has three values:

| Value | What it lists |
|---|---|
| `AIGC` | Virtual-avatar assets you created |
| `LivenessFace` | Real-person assets, including ones another account authorized to you |
| `All` | Both — the node issues one query per type and merges the results |

Ark accepts only one group type per request, so `All` costs two API calls.

### Draft mode (Seedance 2.5)

Turning on `draft` locks `resolution` to `480p` in the node UI, because Ark
rejects any other resolution for a draft.

```
ArkSD Seedance 2.5 (draft=true, resolution=480p)
    ├── VIDEO     -> preview the 480p draft
    └── task_id   -> ArkSD Draft to Video -> VIDEO (1080p) -> SaveVideo
```

Draft mode is two separately billed tasks. The draft task id is valid for 7
days. `ArkSD Draft to Video` reuses the draft's prompt, references, duration,
ratio, seed, and audio setting automatically; it only lets you re-specify
`output_format`, `watermark`, `return_last_frame`, `priority`, and
`execution_expires_after`.

### Non-blocking submission

```
ArkSD Seedance 2.5 (non_blocking=true) ──task_id──> (save it)
ArkSD Query Task (task_id=...) ──VIDEO──> SaveVideo
```

### Putting the seed in the filename

`SaveVideo` renders an inline preview and saves the file. To include the seed
in the filename, connect the node's `seed` output through a convert-to-string
and a text concatenate node into `SaveVideo`'s `filename_prefix`.

## Asset list cache

The asset list is cached for **5 minutes**. Generating a video takes at least
that long, so a change you make in the Ark console during a run is picked up on
the next run. Toggle `refresh` on the **ArkSD Asset** node to force an
immediate re-fetch.

## Changing credentials requires a restart

The `customName` dropdowns are built when the node definitions are registered at
startup, which is a ComfyUI limitation. If you add or rename an entry in
`api_keys.json` or `ak_sk.json`, restart ComfyUI for it to appear. Editing only
the secret value of an existing entry takes effect immediately.

## Cancelling tasks

Ark only allows cancelling a task while it is still **queued**. A task that has
started running cannot be cancelled.

- **While a generation node is waiting**, press ComfyUI's **Cancel** button.
  The node cancels the remote task and stops waiting.
- **For any other task**, use the **Cancel** button on the **ArkSD Task List**
  node. It works even while the ComfyUI queue is busy, because it does not go
  through the execution queue.

## Model availability

There is no API that reports which models your account has opened. If you
submit to a model you have not opened, the node stops with a clear error naming
the model. Open it in the Ark console (Model Square → the Seedance model →
Open) and retry.

## Notes

- Task ids and video URLs are only kept for a limited time. Video URLs expire
  after 24 hours, and Seedance 2.5 video URLs have a 100-download limit.
- The task list only shows the last 7 days of tasks.
- Seedance 2.5 and 2.0 do not accept reference images or videos containing a
  real human face directly. Use an authorized asset from your asset library
  instead.

## License

MIT. See [LICENSE](LICENSE).
