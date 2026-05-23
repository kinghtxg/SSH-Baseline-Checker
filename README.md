# SSH-Baseline-Checker v0.1

SSH 远程安全基线巡检工具。通过交互式 Shell 对 Linux 服务器批量执行安全检查，支持 su root 提权、前端可视化管理检查项、自动生成终端截图和巡检报告。

## 功能特性

- **交互式 Shell**：基于 Paramiko invoke_shell 的真实交互式终端体验
- **su root 提权**：普通账号通过 `su - root` 切换 root，执行高权限检查命令
- **单账号检查**：独立页面对单一主机快速执行安检
- **批量检查**：按账号组批量巡检多台主机
- **检查项管理**：分组管理检查项，支持克隆、批量删除，每条检查项可包含多条命令分别设置正则
- **终端截图**：命令执行结果自动生成真实终端风格截图
- **内置工具箱**：Ping / Telnet / Curl / Web SSH 终端
- **报告管理**：历史报告持久化存储与查看

## 技术栈

| 层面 | 技术 |
|------|------|
| 后端框架 | Flask 3.0 + Flask-SocketIO 5.3 |
| 数据库 | SQLite + SQLAlchemy |
| SSH 引擎 | Paramiko 3.4 (invoke_shell 交互模式) |
| 截图引擎 | Pillow 10.3 |
| 前端 | Jinja2 + Tailwind CSS + Socket.IO |
| 测试 | Pytest + pytest-cov |

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动应用
python app.py

# 3. 浏览器访问
http://localhost:38800
```

首次启动自动创建 `data/` 目录并初始化数据库，包含默认检查项分组「系统安全巡检」。

## 项目结构

```
SSH-Baseline-Checker_v0.1/
├── app.py                  # Flask 主程序（路由 / API / 工具）
├── models.py               # 6 个数据模型 + 默认数据初始化
├── ssh_engine.py           # SSH 交互式 Shell + su root 提权
├── screenshot.py           # 终端截图生成（含 ANSI 清理）
├── requirements.txt
├── .env.example
├── templates/
│   ├── base.html           # 基础布局 + 侧边栏 + 工具箱
│   ├── index.html          # 批量巡检页
│   ├── single_inspect.html # 单账号检查页
│   ├── items.html          # 检查项管理页
│   ├── accounts.html       # 账号组管理页
│   ├── reports.html        # 报告列表页
│   └── report_detail.html  # 报告详情页
├── static/                 # 静态资源
├── tests/                  # 单元测试 + 集成测试
└── data/                   # SQLite 数据库（自动生成）
```

## 使用指南

### 单账号检查

访问 `/inspect/single` → 填写主机信息 → 测试连接 → 选择检查项分组 → 开始检查。

### 批量检查

1. 在「账号管理」创建账号组，添加多台主机
2. 在「检查项管理」配置检查项和命令
3. 在「巡检」页选择账号组和检查项分组，执行批量检查
4. 在「报告」页查看历史结果

### su root 提权

检查命令勾选「需要 root 权限」后，引擎先通过 `su - root` 切换 root，再执行命令。需在主机配置中填写 root 密码。

### 工具面板

页面左侧可展开工具箱：

| 工具 | 用途 |
|------|------|
| SSH 终端 | Web 端直接连接主机操作 |
| Ping | 可达性测试 |
| Telnet | 端口连通性测试 |
| Curl | HTTP 请求测试 |

## 配置

复制 `.env.example` 为 `.env`，可选配置：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| SECRET_KEY | Flask 密钥 | 需自行生成 |
| DATABASE_URI | 数据库路径 | sqlite:///data/inspector.db |
| HOST | 监听地址 | 0.0.0.0 |
| PORT | 监听端口 | 38800 |

## 测试

```bash
python -m pytest tests/ -v
python -m pytest tests/ --cov=. --cov-report=html
```

## 安全提醒

- 目标主机密码存储在本地 SQLite 中，请限制数据库文件访问权限
- SECRET_KEY 务必改为随机字符串
- 生产环境建议配置 HTTPS 和访问认证

## License

MIT