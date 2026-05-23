# 贡献指南

欢迎为 SSH-Baseline-Checker 项目贡献代码！本指南将帮助您了解项目的开发流程、代码规范和提交流程。

## 开发环境搭建

### 1. 克隆项目

```bash
git clone https://github.com/your-org/SSH-Baseline-Checker.git
cd SSH-Baseline-Checker
```

### 2. 创建虚拟环境

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/macOS
python3 -m venv venv
source venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt  # 开发依赖
```

### 4. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，设置必要的环境变量
```

## 代码规范

### Python 代码风格

本项目遵循 [PEP 8](https://pep8.org/) 规范，使用以下工具进行代码检查：

```bash
# 代码格式化
black .

# 导入排序
isort .

# 代码检查
flake8 .

# 类型检查（可选）
mypy .
```

### 文件命名规范

- Python 文件：`snake_case.py`
- 测试文件：`test_snake_case.py`
- 配置文件：`snake_case.ext`
- 模板文件：`snake_case.html`

### 代码结构

```python
# 1. 导入语句（标准库、第三方库、本地模块）
import os
import sys
from typing import Optional, List

import paramiko
from flask import Flask

from models import db

# 2. 常量定义
DEFAULT_PORT = 22
MAX_RETRIES = 3

# 3. 类定义（按字母顺序）
class SSHClient:
    """SSH客户端类，用于管理SSH连接"""
    
    def __init__(self, host: str, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.client = None
    
    def connect(self) -> bool:
        """建立SSH连接"""
        pass

# 4. 函数定义
def clean_ansi(text: str) -> str:
    """清理ANSI转义序列"""
    pass

# 5. 主程序入口
if __name__ == "__main__":
    main()
```

### 文档字符串

所有公共函数、类和方法必须包含文档字符串：

```python
def execute_command(command: str, timeout: int = 30) -> CommandResult:
    """
    执行SSH命令并返回结果。
    
    Args:
        command: 要执行的命令字符串
        timeout: 命令超时时间（秒）
    
    Returns:
        CommandResult对象，包含输出、退出码等信息
    
    Raises:
        SSHTimeoutError: 命令执行超时
        SSHExecutionError: 命令执行失败
    """
    pass
```

### 类型注解

所有函数参数和返回值应包含类型注解：

```python
def parse_host_config(host_config: Dict[str, Any]) -> HostInfo:
    """解析主机配置"""
    pass
```

## 测试规范

### 测试文件结构

```python
"""
模块单元测试 - 测试模块功能
"""
import unittest
from unittest.mock import patch, Mock

from ssh_engine import SSHClient


class TestSSHClient(unittest.TestCase):
    """测试SSH客户端类"""
    
    def setUp(self):
        """测试前置条件"""
        self.client = SSHClient("localhost", 22)
    
    def test_connect_success(self):
        """测试连接成功"""
        with patch("paramiko.SSHClient") as mock_client:
            mock_instance = Mock()
            mock_client.return_value = mock_instance
            result = self.client.connect()
            self.assertTrue(result)
    
    def test_connect_failure(self):
        """测试连接失败"""
        pass
    
    def tearDown(self):
        """测试后置清理"""
        pass
```

### 测试命名规范

- 测试类：`Test[ClassName]`
- 测试方法：`test_[scenario]_[expected_result]`
- 测试文件：`test_[module_name].py`

### 测试覆盖率要求

- 核心模块：≥90%
- 一般模块：≥80%
- 工具模块：≥70%

## Git 工作流

### 分支策略

- `main`：主分支，用于生产环境部署
- `develop`：开发分支，集成功能分支
- `feature/*`：功能分支，开发新功能
- `bugfix/*`：修复分支，修复bug
- `hotfix/*`：热修复分支，紧急修复生产环境问题

### 提交信息规范

使用 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

```
<type>(<scope>): <subject>

<body>

<footer>
```

**类型（type）**：
- `feat`：新功能
- `fix`：修复bug
- `docs`：文档更新
- `style`：代码格式调整（不影响功能）
- `refactor`：代码重构
- `test`：测试相关
- `chore`：构建过程或辅助工具变动

**示例**：
```
feat(ssh): 添加交互式Shell支持

- 实现WebSocket实时通信
- 支持ANSI颜色显示
- 添加键盘事件处理

Closes #123
```

### Pull Request 流程

1. **创建分支**
   ```bash
   git checkout -b feature/your-feature
   ```

2. **开发功能**
   ```bash
   # 编写代码
   # 添加测试
   # 更新文档
   ```

3. **提交代码**
   ```bash
   git add .
   git commit -m "feat: 添加新功能"
   git push origin feature/your-feature
   ```

4. **创建Pull Request**
   - 在GitHub上创建PR到 `develop` 分支
   - 填写PR模板
   - 关联相关Issue

5. **代码审查**
   - 至少需要1位核心成员审查通过
   - 通过所有CI检查
   - 解决审查意见

6. **合并代码**
   - 使用 "Squash and merge" 合并
   - 删除功能分支

## 开发流程

### 1. 功能开发

1. 从 `develop` 分支创建功能分支
2. 实现功能代码
3. 编写单元测试
4. 更新相关文档
5. 运行测试确保通过

### 2. Bug修复

1. 从 `develop` 分支创建修复分支
2. 定位问题并修复
3. 添加回归测试
4. 验证修复效果
5. 提交PR

### 3. 代码审查要点

- **功能正确性**：是否满足需求
- **代码质量**：是否符合规范
- **测试覆盖**：是否有足够测试
- **文档更新**：是否更新相关文档
- **性能影响**：是否影响系统性能
- **安全考虑**：是否存在安全隐患

### 4. CI/CD流程

项目使用GitHub Actions进行持续集成：

```yaml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
      - run: pip install -r requirements.txt
      - run: pip install -r requirements-dev.txt
      - run: python -m pytest tests/ --cov=. --cov-report=xml
      - run: flake8 .
      - run: black --check .
```

## 文档规范

### 1. 代码文档

- 所有公共API必须包含文档字符串
- 复杂算法需要注释说明
- 特殊处理需要说明原因

### 2. 用户文档

- README.md：项目概述和快速入门
- API文档：API接口说明
- 部署文档：部署和配置说明
- 用户手册：详细使用指南

### 3. 开发文档

- 架构设计文档
- 数据库设计文档
- 测试计划文档
- 贡献指南

## 问题反馈

### 1. 报告Bug

使用GitHub Issues报告问题：

**Bug报告模板**：
```markdown
**描述**
清晰描述问题现象

**重现步骤**
1. 
2. 
3. 

**预期行为**
期望的结果

**实际行为**
实际的结果

**环境信息**
- 操作系统：
- Python版本：
- 项目版本：
- 其他信息：

**截图/日志**
相关截图或日志
```

### 2. 功能建议

**功能建议模板**：
```markdown
**功能描述**
详细描述需要的功能

**使用场景**
在什么情况下需要此功能

**建议方案**
建议的实现方式

**替代方案**
其他可能的解决方案
```

## 行为准则

### 1. 尊重他人

- 保持专业和尊重的沟通方式
- 接受建设性批评
- 帮助他人学习和成长

### 2. 包容性

- 欢迎不同背景的贡献者
- 使用包容性语言
- 尊重不同的观点和经验

### 3. 责任

- 对自己的代码负责
- 及时响应审查意见
- 帮助维护项目质量

## 联系方式

- **项目维护者**：[维护者姓名]
- **邮件列表**：[邮件地址]
- **Slack频道**：[频道链接]
- **问题反馈**：[GitHub Issues](https://github.com/your-org/SSH-Baseline-Checker/issues)

---

感谢您对 SSH-Baseline-Checker 项目的贡献！