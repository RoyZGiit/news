# AI News Aggregator

AI 行业信息聚合系统 —— 自动监控 GitHub、HuggingFace、Reddit、Arxiv、Twitter 等数据源，使用 LLM 生成每日/每周中文简报，以静态网站形式展示。

## 架构

```
本地 Mac Mini                              远程服务器
┌──────────────────────────┐          ┌─────────────┐
│  Crawlers (7个数据源)      │          │   Nginx     │
│  → SQLite 存储            │  rsync   │   ↓         │
│  → LLM 摘要 + 评分        │ ──────→  │  静态 HTML  │
│  → 简报生成               │          │  /CSS/JSON  │
│  → 静态站点构建            │          └─────────────┘
└──────────────────────────┘
```

- **本地**：运行爬虫、AI 摘要、简报生成等所有重活
- **服务器**：仅需 Nginx 托管静态文件，内存占用 < 50MB

## 数据源

| 数据源 | 内容 | 频率 |
|--------|------|------|
| GitHub | Trending repos + AI 厂商 releases | 每 6 小时 |
| HuggingFace | Trending models / papers / spaces | 每 6 小时 |
| Reddit | r/MachineLearning, r/LocalLLaMA 等 | 每 4 小时 |
| Twitter/X | 关键 AI 账号推文 (via RSSHub) | 每 4 小时 |
| Arxiv | cs.AI / cs.CL / cs.LG 最新论文 | 每 12 小时 |
| Leaderboard | LMSYS Arena / Open LLM LB | 每 24 小时 |
| 厂商博客 | OpenAI / Anthropic / Google AI / Meta AI Blog | 每 6 小时 |

## 快速开始

### 1. 安装依赖

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置

```bash
# 复制环境变量模板并填写 API keys
cp .env.example .env

# 编辑配置文件（数据源、LLM、远程服务器等）
vim config.yaml
```

最低配置：只需设置 `OPENAI_API_KEY`（或其他 LLM provider 的 key）。

### 3. 运行

```bash
# 一次性运行完整流程（爬虫 → 摘要 → 简报 → 构建站点 → 推送）
python main.py pipeline

# 或者分步运行
python main.py crawl       # 只运行爬虫
python main.py summarize   # 只运行 AI 摘要
python main.py briefing    # 只生成简报
python main.py build       # 只构建静态站点
python main.py push        # 只推送到服务器

# 持续运行模式（定时调度）
python main.py run

# 查看状态
python main.py status
```

### 4. 服务器配置

```bash
# 在远程服务器上
sudo cp deploy/nginx.conf /etc/nginx/sites-available/ai-news
sudo ln -s /etc/nginx/sites-available/ai-news /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## 命令参考

| 命令 | 说明 |
|------|------|
| `python main.py run` | 启动定时调度器，持续运行 |
| `python main.py crawl` | 运行所有启用的爬虫 |
| `python main.py summarize` | AI 摘要未处理的文章 |
| `python main.py briefing` | 生成每日简报 |
| `python main.py briefing --weekly` | 生成每周简报 |
| `python main.py build` | 构建静态 HTML 站点 |
| `python main.py push` | rsync 推送到远程服务器 |
| `python main.py pipeline` | 完整流水线 |
| `python main.py status` | 查看系统状态 |

## 配置说明

### LLM 支持

通过 LiteLLM 支持多个 LLM provider，在 `config.yaml` 中切换：

```yaml
llm:
  provider: "openai"       # openai / anthropic / deepseek
  model: "gpt-4o-mini"    # 任何 LiteLLM 支持的模型
```

### 数据源开关

在 `config.yaml` 中通过 `enabled: false` 禁用不需要的数据源。

## 项目结构

```
news/
├── main.py                 # CLI 入口
├── config.yaml             # 配置文件
├── .env                    # API Keys (不入版本库)
├── src/
│   ├── config.py           # 配置加载
│   ├── database.py         # 数据库模型
│   ├── scheduler.py        # 定时任务调度
│   ├── sources/            # 7 个数据源爬虫
│   ├── ai/                 # LLM 客户端 + 摘要 + 简报
│   ├── generator/          # Markdown + 静态站点生成
│   ├── publisher/          # rsync 推送
│   └── templates/          # HTML 模板
├── briefings/              # Markdown 简报归档
├── site/                   # 生成的静态站点
└── deploy/                 # Nginx 配置
```
