# image-provenance-mcp 中文速览

看图鉴伪的 MCP server。按正确的顺序回答「这张图是 AI 生成的吗 / 被改过吗」：

1. **先读 C2PA 内容凭证**（签名、可校验）。有清单就直接给结论，不再往下走。
2. **没有清单才跑像素启发式**（噪声 / ELA / 频谱 / 颜色 / EXIF），并且明确标注这只是猜测。

不用 API key，不联网，不上报数据。第一档只需要 Python 标准库 + 系统自带的 `openssl`。

## 为什么顺序不能反

同一张 ChatGPT(gpt-image) 生成的 PNG：

| 信号 | 结论 |
|---|---|
| 噪声均匀度 8.27 | 「看着像自然照片」 |
| 无相机 EXIF | 「可疑」 |
| **C2PA 清单** | **`trainedAlgorithmicMedia`，ChatGPT 生成** |

启发式给出了两个互相矛盾的弱信号，最后大概率输出一句自信的「可能为 AI 生成」；而清单给出的是事实。
反过来，微信转发过的图因为 EXIF 被剥离，启发式会仅凭「没有相机信息」就喊 AI——这是同一套逻辑的反向误判。

启发式描述的是**痕迹**，C2PA 描述的是**作者**。别让后者被前者冒充。

## 装

```bash
pip install -e '.[pixel]'    # 只要 C2PA 的话去掉 [pixel]
```

## 用

```bash
image-provenance photo.jpg              # 两档自动
image-provenance photo.jpg --mode c2pa  # 只看签名
image-provenance photo.jpg --json
image-provenance --mcp                  # 作为 MCP server
```

MCP 工具：`image_provenance`（推荐入口）、`c2pa_inspect`，以及第二档的
`full_forensic_report` / `noise_map` / `error_level_analysis` / `frequency_analysis` /
`spectral_decay_analysis` / `color_analysis` / `metadata_check`。

## 判定

`AI_GENERATED` / `EDITED` / `CAPTURED` / `INVALID_HASH`（签完之后被改过）/ `NO_C2PA`。

`NO_C2PA` 不是罪证：绝大多数相机、所有聊天软件、所有截图和 CDN 重编码都会把清单抹掉。

## 已验证

- 真清单：`AI_GENERATED`，OpenAI Media Service API，链 `OpenAI Media Service` ← `Trufo CA`
- 硬绑定：重算 sha256 与签名值一致
- **篡改测试**：改 IDAT 里一个 bit → `INVALID_HASH`，两种校验算法算出的值一致（说明是内容变了，不是算法错）
- 20 个单元测试通过

## 边界（很重要）

- **不做密码学验签**：只校验 sha256 硬绑定 + 打印证书链，不验签、不查吊销、不校信任锚。所以
  `INVALID_HASH` 可信，"证书链可信"目前只到"看起来对"。要完整校验请用官方 `c2patool` / `c2pa-python`。
- JPEG 的 APP11 多段重组照规范实现，但没有真实签名 JPEG 做过端到端验证。
- 不解析旧式 XMP 里的 `c2pa` 字段。
- 第二档的阈值来自上游项目，样本量小，只能当提示。

## 许可

本项目 MIT。第二档代码 vendored 自 [surewht/image-forensics-mcp](https://github.com/surewht/image-forensics-mcp)（MIT, © 2026 surewht），
详见 [NOTICE.md](NOTICE.md)。
