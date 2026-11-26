# 电脑端 AI 网关接口

SDK 复用原项目 `cloud_server` 的 HTTP 接口。这里不改变 [USB 音频协议](audio-v1.md)。旧 `pc_server` 的 `/v1/job` 和 `/v1/audio` 路由是另一套协议，不应填作本客户端的网关。可为原 `cloud_server` 使用本机模拟提供方或现有生产提供方，不需要新增服务器。

| 操作 | 路径（`/voice-api/v1` 前缀） | 内容 |
|---|---|---|
| 语音问答 | `POST /dialogue` | `audio/L16`，按本服务约定为 16 kHz、单声道、16-bit 小端裸 PCM，来自 `AudioClip.pcm`。不是 WAV。 |
| 文字问答 | `POST /text-dialogue` | JSON `{"text": "你好"}`；最多 8000 字符。 |
| 查询进度 | `GET /jobs/{job_id}` | 提交返回 202 和 32 位小写十六进制任务号。轮询 `queued/transcribing/generating`，`completed/failed` 停止。读取 `recognized_text` 和 `answer_text`。 |
| 查询已就绪的分段 | `GET /jobs/{job_id}/segments?after=N` | 启用 `on_text` 或 `on_segment` 时使用。从 `after=-1` 开始，按连续 `index` 读取 `text`。逐段播报时还校验 `sample_rate` 和 `byte_count`。服务器完成后查询任务详情，并核对已处理的段数。 |
| 下载单段回复 | `GET /jobs/{job_id}/segments/{index}/audio` | 启用 `on_segment` 时逐段下载，按 16 kHz PCM 解析。以校验过的任务号和段号构造路径。`robot.ai.record_end()` 下载后立即调用设备播放，不等待整段音频接口。 |
| 下载完整回复 | `GET /jobs/{job_id}/audio` | 任务完成后下载已拼接 PCM，要求 `audio/L16`、`X-Audio-Sample-Rate: 16000`，大小最多 960000 字节。 |

每次请求带 `X-Device-ID` 和 `Authorization: Bearer <设备 Token>`，不使用管理员或厂商凭据。远程使用 HTTPS；HTTP 仅允许回环地址。SDK 不跟随重定向或服务返回的 URL，固定由配置地址与已验证的任务号构造请求；不请求设备本地动作。服务器可能记录录音、文字和用量，按管理员设置决定。

网关本地模拟测试可在原项目启动 `cloud_server` 的 mock 模式、注册一个测试设备，再在示例选择相应服务器地址。mock 使用模拟识别、回复和合成音，适合验证 HTTP 与接口；真实 ASR/LLM/TTS 和音频实物效果须分别验证。

客户端把 HTTP 401 归为 `invalid_credentials`。HTTP 402、带有明确额度错误的 HTTP 429 或带有明确额度错误的失败任务归为 `quota_exhausted`，普通 HTTP 429 归为 `rate_limited`。任务未报告原因时，客户端提示任务失败并给出任务号。原始服务错误正文不输出到控制台。
