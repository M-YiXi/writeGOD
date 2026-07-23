# 小说知识引擎

<p align="center" style="font-size: 1.1em; line-height: 1.8; color: #555; max-width: 780px; margin: 1.5em auto;">
  AI知识图谱驱动的小说创作辅助平台<br>
  支持百万量级文字，超高并发数，可搭配本地向量模型/本地大语言模型以及向量库进行使用。<br>
  将你的素材和小说文本转化为可视化的概念网络，帮你理清人物关系、追踪伏笔、检测逻辑漏洞、与角色对话。
</p>

<br>

<!-- 首页截图（大图） -->
<p align="center">
  <img src="截图/%E6%88%AA%E5%B1%8F2026-07-23%2014.31.42.png" alt="writeGOD 首页" width="90%" style="border-radius: 12px; box-shadow: 0 8px 30px rgba(0,0,0,0.12);">
  <br>
  <em>首页 & 双模式入口：素材大纲与小说推演</em>
</p>

<br>

<!-- 两张运行截图 -->
<table align="center" style="border: none; border-collapse: collapse; width: 90%;">
  <tr style="border: none;">
    <td width="50%" style="border: none; padding: 8px; text-align: center;">
      <img src="截图/%E6%88%AA%E5%B1%8F2026-07-23%2011.52.17.png" alt="首页入口截图" width="100%" style="border-radius: 10px; box-shadow: 0 4px 16px rgba(0,0,0,0.1);">
      <br>
      <em>素材大纲与小说推演</em>
    </td>
    <td width="50%" style="border: none; padding: 8px; text-align: center;">
      <img src="截图/%E6%88%AA%E5%B1%8F2026-07-23%2012.58.12.png" alt="图谱可视化截图" width="100%" style="border-radius: 10px; box-shadow: 0 4px 16px rgba(0,0,0,0.1);">
      <br>
      <em>知识图谱可视化与AI分析面板</em>
    </td>
  </tr>
</table>

<br>

## 功能

- **素材大纲**：导入参考资料（PDF/TXT/MD），自动提取实体并构建关联网络，适合写作前的世界观搭建
- **小说推演**：导入整本小说，构建人物关系图谱，与角色对话，检测逻辑漏洞，发现未回收的伏笔

注：目前版本的两种功能近似度较高，都是基于图谱构建的关系网络，只不过开放的部分接口不同

### 核心能力

| 功能 | 说明 |
|:-----|:-----|
| **知识图谱构建** | LLM 驱动的实体/关系提取 + Neo4j 图谱存储 + D3.js 力导向节点图可视化 |
| **SSE 流式进度** | 构建过程实时推送进度（实体数/关系数/处理速度/已用时），节点渐入显示 |
| **角色对话** | 在节点图选定角色后对话，向量检索记忆片段注入，角色回答可引用原文 |
| **智能问答** | 自然语言查询，向量检索相关段落 + LLM 总结回答 |
| **逻辑漏洞检测** | 死亡角色后续活动检测 + 角色设定一致性检测（LLM 比对矛盾） |
| **伏笔追踪** | 低关联度节点识别 + LLM 判断是否为伏笔及是否回收 |
| **角色一致性检测** | 同一角色的所有描述比对，找出互相矛盾的设定 |
| **相似情节检测** | 向量余弦相似度找出语义重复的场景和表达 |

## 技术栈

- **前端**：Vue 3 + D3.js（力导向节点图）
- **后端**：Python Flask
- **图数据库**：Neo4j 5.x（含向量索引）
- **LLM**：支持任意 OpenAI SDK 兼容的 LLM API（DeepSeek / 火方引擎 / 阿里百炼等）
- **向量嵌入**：支持独立配置（Ollama / API 均可）


## 快速开始

### 前置要求

| 工具 | 版本 | 说明 |
|------|------|------|
| Node.js | 18+ | 前端运行环境 |
| Python | 3.9+ | 后端运行环境 |
| Neo4j | 5.x | 图数据库 |

> 以下所有命令默认在**项目根目录** `writeGOD-main/` 下执行。请先 `cd` 到项目根目录：
> ```bash
> cd /你的路径/writeGOD-main
> ```

### 1. 配置环境变量

在**项目根目录**创建 `env.txt`（或从 `env.example` 复制），填入配置：

```bash
# 在项目根目录执行（或者直接打开此文件或许更快）
cp env.example env.txt
# 然后编辑 env.txt，填入你的 API 密钥和 Neo4j 密码
```

配置内容：

```env
# LLM API 配置（支持任意 OpenAI SDK 兼容的 LLM API）
# 注意：LLM_BASE_URL 需填写完整端点地址，系统不会自动追加 /v1
# DeepSeek 示例：  https://api.deepseek.com/v1
# 火方引擎示例：   https://ark.cn-beijing.volces.com/api/coding/v3
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL_NAME=期待一手DeepSeek-V4正式版

# 向量嵌入配置
EMBEDDING_BASE_URL=http://127.0.0.1:1234/v1
EMBEDDING_MODEL_NAME=your_embedding_model
EMBEDDING_API_KEY=your_key

# Neo4j 图数据库配置
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password（你的密码）
```

### 2. 安装依赖

```bash
# 1) 安装根目录 Node 依赖（在项目根目录执行）
npm install

# 2) 安装前端依赖
cd frontend
npm install
cd ..    # 回到项目根目录

# 3) 安装后端依赖（在 backend 目录执行）
cd backend
python3 -m venv .venv
source .venv/bin/activate      # 激活虚拟环境（Windows 用 .venv\Scripts\activate）
pip install -r requirements.txt
cd ..    # 回到项目根目录
```

> 如果已安装 `uv`，后端依赖也可用 `npm run setup:backend` 一键安装。

### 3. 启动服务

**确保 Neo4j 已运行**，然后在**项目根目录**执行：

```bash
# 在项目根目录执行，同时启动前后端
npm run dev
```

启动后访问：
- 前端页面：`http://localhost:3000`
- 后端 API：`http://localhost:5001`

单独启动（均在**项目根目录**执行）：

```bash
npm run backend   # 仅启动后端
npm run frontend  # 仅启动前端
```

> 后端依赖需要在 `backend/` 目录下激活虚拟环境后才能运行。
> 如果用 `npm run dev` 一键启动则无需手动激活，脚本会自动处理。


## 参考

基于 [MiroFish-Refactor-zh](https://github.com/M-YiXi/MiroFish-Refactor-zh) 改造，（另外要感谢参考项目的原始项目）保留了核心的图谱引擎和节点图界面，加入针对小说创作场景的专属能力。去除了大部分无用功能。并且重构了大多数的前端与后端。

## License

AGPL-3.0
