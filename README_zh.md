<div align="center">

<img src="kbase/static/logos/kbase-logo.svg" alt="KBase" width="80" height="80">

# KBase

**真正能找到东西的本地知识库。**

把任何文件夹变成可搜索、AI 驱动的知识库。
不上传云端，不锁定平台，数据始终在你的电脑上。

[![Release](https://img.shields.io/github/v/release/PenguinMiaou/kbase?style=flat-square)](https://github.com/PenguinMiaou/kbase/releases)
[![License](https://img.shields.io/github/license/PenguinMiaou/kbase?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-blue?style=flat-square)]()

[快速开始](#快速开始) | [功能特性](#功能特性) | [知识图谱](#知识图谱) | [架构](#架构) | [命令行](#命令行) | [English](README.md)

<img src="docs/screenshots/chat-demo.png" alt="KBase Chat" width="800">

</div>

---

## 为什么选 KBase？

你有 300GB 的工作文件：PPT、PDF、Word、Excel、邮件、会议记录。找一个东西要打开 20 个文件夹，每个 Ctrl+F。

KBase 一次索引所有文件，然后让你**在一个地方搜索所有文档**，并**用任何 LLM 和文档对话**。

```
"找下 Q3 的收入数据在哪个表里"
-> 找到了：财务报告_2024Q3.xlsx (Sheet: Revenue, Row 42)

"架构组对数据平台的方案是什么？"
-> 来源：IT架构方案v3.pptx (Slide 14), 数据平台规划.docx (Section 2.3)
```

## 功能特性

### 13 阶段自适应搜索管线

不只是关键词匹配。KBase 运行**13 阶段检索管线**，根据查询难度自动升级：

```
Query -> 同义词扩展 -> [HyDE -> 多角度重写]* -> 语义 + 关键词 + 文件名
-> RRF 融合 -> 时间衰减 -> 去重 -> 交叉编码器重排 -> 父块扩展
-> 目录优先级 -> 图谱增强 -> 表格提示
                                    * 仅在需要时触发（自适应）
```

| 技术 | 作用 |
|------|------|
| **HyDE** | LLM 先生成假设答案，用其 embedding 搜索（比短查询匹配更准） |
| **Multi-Query** | LLM 从不同角度改写查询，提高召回率 |
| **Parent-Child 分块** | 小块精准匹配，大块提供上下文 |
| **语义分块** | 按段落/句子切分（中文感知：。！？；），非固定字符数 |
| **交叉编码器重排** | BAAI/bge-reranker-v2-m3 对 top 结果重新打分 |
| **自适应升级** | 简单查询 <1s，复杂查询自动启用完整管线（2-3s） |
| **自动术语表** | 从文档中提取领域术语，自动扩展搜索 |
| **图谱增强** | 手动确认的文档关系提升搜索排序 |

### 知识图谱

<img src="docs/screenshots/graph-dark.png" alt="Knowledge Graph" width="700">

Obsidian 风格的图谱可视化，**图谱 + 白板双模式**：

- **图谱模式** -- 力导向布局（Cytoscape.js + fcose），基于语义相似度自动计算关系
- **白板模式** -- 拖拽固定，手动在文档间画线连接
- **三层边**：自动（虚线，低透明度）/ 确认（实线）/ 标注（实线 + 箭头 + 标签）
- 悬停高亮邻居节点，双击进入局部图（2 跳子图）
- 右键菜单：节点（打开文件、局部图、固定位置）、边（确认、标注、删除）
- 搜索过滤：输入关键词高亮匹配节点，其余暗化
- 暗色/亮色主题，匹配 Obsidian 美学风格

### 20+ LLM 提供商

| 国际 | 国内 | 本地 |
|------|------|------|
| Claude Sonnet/Opus | 通义千问 Plus/Max | Ollama |
| GPT-4o / Mini | DeepSeek Chat/R1 | Claude CLI |
| Gemini 2.5 Flash/Pro | 智谱 GLM-4 Flash | Qwen CLI |
| | Kimi / 豆包 / MiniMax | LLM CLI |
| | 混元 / 文心 | Custom (OpenAI 兼容) |

### 多模态视觉

从 PPTX 和 PDF 中提取图片，用视觉 LLM 生成描述（8 款模型可选），让架构图、流程图也能被搜索到。

### 6 引擎网络搜索

DuckDuckGo / Brave / Google (Serper) / Bing 国际版 / 搜狗 / 微信文章，按语言自动路由。

### 5 种搜索模式

| 模式 | 功能 |
|------|------|
| **直聊** | 纯 LLM 对话 + 全局记忆，不搜索 |
| **知识库** | 仅搜索本地索引文件 |
| **网络** | 多引擎互联网搜索 |
| **混合** | 本地 + 网络联合搜索 |
| **研究** | 多轮深度研究，迭代搜索和综合分析（生成完整报告） |

### 文件格式支持

| 格式 | 处理方式 |
|------|----------|
| `.pptx` `.ppt` | 逐页文本 + 表格 + 图片提取（Vision LLM） |
| `.docx` `.doc` | 段落、标题、表格 |
| `.xlsx` `.xls` `.csv` | 全文搜索 + SQL 查询结构化数据 |
| `.pdf` | 逐页文本 + 图片提取（Vision LLM） |
| `.md` `.txt` `.html` | 直接文本索引 |
| `.mp3` `.m4a` `.wav` `.mp4` | 语音转文字（Whisper / DashScope / Gemini） |
| `.eml` `.mbox` | 邮件解析（MIME 头解码） |
| `.zip` `.tar` `.gz` `.7z` | 自动解压并索引内容 |
| `.rar` | RAR 解压（rarfile 纯 Python） |

### Claude 风格 UI

- 三栏布局 + 研究报告 artifact 面板
- 会话管理（自动生成标题）
- 7 个助手预设（MBTI 人格 + 自定义）
- 暗色/亮色主题 + 中英文切换
- 导入进度条（SSE）支持暂停/停止/恢复
- 跨标签页同步（BroadcastChannel）
- 全局记忆系统
- 知识图谱标签页

## 快速开始

### macOS (DMG)

从 [Releases](https://github.com/PenguinMiaou/kbase/releases) 下载 `KBase-0.5.1.dmg` -> 拖到 Applications -> 打开。

### Windows (EXE)

从 [Releases](https://github.com/PenguinMiaou/kbase/releases) 下载 `KBase-0.5.1-Windows.zip` -> 解压 -> 运行 `KBase.exe`。

### 从源码

```bash
git clone https://github.com/PenguinMiaou/kbase.git
cd kbase
bash install.sh          # macOS/Linux
# 或
install.bat              # Windows

./kbase-cli ingest ~/Documents/work    # 索引文件
./kbase-cli web                        # 打开 http://localhost:8765
```

## 命令行

```bash
kbase ingest /path/to/files           # 索引（跳过未变更文件）
kbase ingest /path --force            # 强制重建索引
kbase search "query"                  # 混合搜索
kbase chat "question"                 # 与 LLM + 知识库对话
kbase sql "SELECT * FROM table"       # SQL 查询表格数据
kbase web                             # 启动 Web UI
```

## 架构

```
kbase/
├── web.py           # FastAPI 服务 + 所有 API
├── chat.py          # 20 LLM 提供商 + 助手预设 + 记忆
├── store.py         # ChromaDB (向量) + SQLite FTS5 (关键词) + 表格 + 图谱表
├── search.py        # 13 阶段自适应管线 (+ 图谱增强)
├── graph.py         # 知识图谱计算 + 边管理
├── enhance.py       # HyDE, 多查询, 重排, 术语表, 查询扩展
├── vision.py        # 视觉 LLM 图片描述 (8 模型)
├── extract.py       # 文件提取器 (PPTX/PDF/DOCX/XLSX/音频/邮件/压缩包/RAR)
├── chunk.py         # 语义分块 + 父子层级
├── ingest.py        # 导入管线（暂停/停止/恢复）
├── websearch.py     # 6 引擎网络搜索
├── agent_loop.py    # 深度研究 Agent
├── config.py        # 模型配置
├── connectors/      # 飞书集成
└── static/          # Claude 风格前端 (HTML/CSS/JS + Cytoscape.js)
```

## 反馈

发现 Bug？有新功能需求？
- [提交 Issue](https://github.com/PenguinMiaou/kbase/issues)
- 设置 -> 反馈 -> 报告问题

## 许可

[MIT License](LICENSE) - 随便用。
