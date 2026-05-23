"""
V4 数据库模型 - 账号组 + 交互式Shell + 多命令
"""
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class AccountGroup(db.Model):
    """账号组 - 一组目标主机"""
    __tablename__ = 'account_groups'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)

    hosts = db.relationship('TargetHost', backref='account_group', lazy=True,
                            cascade='all, delete-orphan',
                            order_by='TargetHost.sort_order')

    def to_dict(self, include_hosts=False):
        d = {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }
        if include_hosts:
            d['hosts'] = [h.to_dict() for h in self.hosts]
        return d


class TargetHost(db.Model):
    """目标主机 - 属于某个账号组"""
    __tablename__ = 'target_hosts'

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('account_groups.id'), nullable=False)
    name = db.Column(db.String(100))           # 别名，如"生产服务器01"
    host = db.Column(db.String(100), nullable=False)   # IP或域名
    port = db.Column(db.Integer, default=22)
    username = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(200), nullable=False)
    can_sudo = db.Column(db.Boolean, default=False)    # 是否可切换root（通过su）
    root_password = db.Column(db.String(200))          # root密码（如果不同）
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self, hide_password=True):
        d = {
            'id': self.id,
            'groupId': self.group_id,
            'name': self.name,
            'host': self.host,
            'port': self.port,
            'username': self.username,
            'canSudo': self.can_sudo,
            'sortOrder': self.sort_order,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }
        if not hide_password:
            d['password'] = self.password
            d['rootPassword'] = self.root_password
        return d


class ItemGroup(db.Model):
    """检查项分组"""
    __tablename__ = 'item_groups'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)

    items = db.relationship('InspectionItem', backref='group', lazy=True,
                            cascade='all, delete-orphan')

    def to_dict(self, include_items=False):
        d = {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'sortOrder': self.sort_order,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }
        if include_items:
            d['items'] = [item.to_dict() for item in
                          sorted(self.items, key=lambda x: x.sort_order)]
        return d


class InspectionItem(db.Model):
    """检查项 - 包含多条命令"""
    __tablename__ = 'inspection_items'

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('item_groups.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    enabled = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    commands = db.relationship('ItemCommand', backref='item', lazy=True,
                               cascade='all, delete-orphan',
                               order_by='ItemCommand.sort_order')

    def to_dict(self, include_commands=True):
        d = {
            'id': self.id,
            'groupId': self.group_id,
            'name': self.name,
            'description': self.description,
            'enabled': self.enabled,
            'sortOrder': self.sort_order,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_commands:
            d['commands'] = [c.to_dict() for c in self.commands]
        return d


class ItemCommand(db.Model):
    """检查项下的单条命令"""
    __tablename__ = 'item_commands'

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('inspection_items.id'), nullable=False)
    command = db.Column(db.Text, nullable=False)
    success_regex = db.Column(db.Text)
    description = db.Column(db.Text)
    require_root = db.Column(db.Boolean, default=False)   # 是否需要root权限
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'itemId': self.item_id,
            'command': self.command,
            'successRegex': self.success_regex,
            'description': self.description,
            'requireRoot': self.require_root,
            'sortOrder': self.sort_order,
        }


class InspectionSession(db.Model):
    """巡检会话"""
    __tablename__ = 'inspection_sessions'

    id = db.Column(db.Integer, primary_key=True)
    host = db.Column(db.String(100), nullable=False)
    port = db.Column(db.Integer, default=22)
    username = db.Column(db.String(100), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('item_groups.id'), nullable=True)
    total_commands = db.Column(db.Integer, default=0)
    success_count = db.Column(db.Integer, default=0)
    fail_count = db.Column(db.Integer, default=0)
    duration = db.Column(db.Float)
    status = db.Column(db.String(20), default='running')
    created_at = db.Column(db.DateTime, default=datetime.now)

    results = db.relationship('InspectionResult', backref='session', lazy=True,
                              cascade='all, delete-orphan',
                              order_by='InspectionResult.id')

    def to_dict(self):
        return {
            'id': self.id,
            'host': self.host,
            'port': self.port,
            'username': self.username,
            'groupId': self.group_id,
            'totalCommands': self.total_commands,
            'successCount': self.success_count,
            'failCount': self.fail_count,
            'duration': self.duration,
            'status': self.status,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }


class InspectionResult(db.Model):
    """巡检结果 - 每条命令一个结果"""
    __tablename__ = 'inspection_results'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('inspection_sessions.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('inspection_items.id'), nullable=True)
    command_id = db.Column(db.Integer, db.ForeignKey('item_commands.id'), nullable=True)
    item_name = db.Column(db.String(200), nullable=False)
    command_text = db.Column(db.Text, nullable=False)
    command_desc = db.Column(db.Text)
    output = db.Column(db.Text)
    success_regex = db.Column(db.Text)
    regex_matched = db.Column(db.Boolean)
    exit_code = db.Column(db.Integer)
    executed = db.Column(db.Boolean, default=False)
    screenshot_path = db.Column(db.String(500))
    duration = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'sessionId': self.session_id,
            'itemId': self.item_id,
            'commandId': self.command_id,
            'itemName': self.item_name,
            'commandText': self.command_text,
            'commandDesc': self.command_desc,
            'output': self.output,
            'successRegex': self.success_regex,
            'regexMatched': self.regex_matched,
            'exitCode': self.exit_code,
            'executed': self.executed,
            'screenshotPath': self.screenshot_path,
            'duration': self.duration,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }


def init_default_data():
    """初始化默认数据"""
    if ItemGroup.query.first():
        return

    # 创建检查项分组
    ig = ItemGroup(name='系统安全巡检', description='标准系统安全检查项', sort_order=10)
    db.session.add(ig)
    db.session.flush()

    defaults = [
        {
            'name': '1. 系统资源限制',
            'description': '检查系统资源限制配置',
            'sort_order': 10,
            'commands': [
                {'command': 'ulimit -a', 'success_regex': r'(core file size|open files|stack size|max user processes)', 'description': '当前资源限制'},
                {'command': 'cat /etc/security/limits.conf', 'success_regex': r'(soft|hard|nofile|nproc)', 'description': 'limits.conf配置'},
            ]
        },
        {
            'name': '2. 内存与Swap',
            'description': '检查内存和swap状态',
            'sort_order': 20,
            'commands': [
                {'command': 'free -h', 'success_regex': r'Mem|Swap', 'description': '内存使用情况'},
                {'command': 'cat /proc/sys/vm/swappiness', 'success_regex': r'^\d+$', 'description': 'swap倾向值'},
            ]
        },
        {
            'name': '3. 防火墙',
            'description': '检查防火墙服务及规则',
            'sort_order': 30,
            'commands': [
                {'command': 'systemctl status firewalld', 'success_regex': r'Active: active \(running\)', 'description': 'firewalld状态'},
                {'command': 'firewall-cmd --list-all', 'success_regex': r'target|interfaces|services|ports', 'description': '防火墙规则'},
                {'command': 'iptables -L -n | head -20', 'success_regex': r'Chain|target|ACCEPT|DROP', 'description': 'iptables规则'},
            ]
        },
        {
            'name': '4. SYN防御',
            'description': 'SYN flood防御机制',
            'sort_order': 40,
            'commands': [
                {'command': 'cat /proc/sys/net/ipv4/tcp_syncookies', 'success_regex': r'^1$', 'description': 'tcp_syncookies'},
                {'command': 'sysctl net.ipv4.tcp_synack_retries', 'success_regex': r'\d+', 'description': 'synack重试次数'},
            ]
        },
        {
            'name': '5. 日志配置',
            'description': '日志轮转策略',
            'sort_order': 50,
            'commands': [
                {'command': 'cat /etc/logrotate.conf', 'success_regex': r'daily|weekly|rotate|compress', 'description': 'logrotate配置'},
                {'command': 'ls /etc/logrotate.d/ | head -10', 'success_regex': r'\w+', 'description': '子配置列表'},
            ]
        },
        {
            'name': '6. SSH安全',
            'description': 'SSH安全配置检查',
            'sort_order': 60,
            'commands': [
                {'command': 'cat /etc/ssh/sshd_config | grep -E "^(Port|PermitRootLogin|PasswordAuthentication|MaxAuthTries)" ', 'success_regex': r'Port|PermitRootLogin|PasswordAuthentication', 'description': 'SSH关键配置'},
                {'command': 'systemctl status sshd', 'success_regex': r'Active: active \(running\)', 'description': 'SSH服务状态'},
            ]
        },
        {
            'name': '7. 系统时间',
            'description': '系统时间同步',
            'sort_order': 70,
            'commands': [
                {'command': 'timedatectl status', 'success_regex': r'Local time|System clock synchronized', 'description': '时间同步状态'},
                {'command': 'date', 'success_regex': r'20\d{2}', 'description': '当前时间'},
            ]
        },
    ]

    for d in defaults:
        item = InspectionItem(group_id=ig.id, name=d['name'],
                              description=d['description'], sort_order=d['sort_order'])
        db.session.add(item)
        db.session.flush()
        for i, c in enumerate(d['commands']):
            cmd = ItemCommand(item_id=item.id, command=c['command'],
                              success_regex=c.get('success_regex'),
                              description=c.get('description'),
                              sort_order=(i + 1) * 10)
            db.session.add(cmd)

    # 创建默认账号组
    ag = AccountGroup(name='默认测试组', description='示例测试服务器')
    db.session.add(ag)
    db.session.flush()

    # 添加测试主机（示例占位符：请通过Web界面或环境变量配置真实主机）
    host = TargetHost(
        group_id=ag.id,
        name='示例测试机',
        host='127.0.0.1',
        port=22,
        username='testuser',
        password='password123',
        can_sudo=False,
        sort_order=10,
    )
    db.session.add(host)

    db.session.commit()
    print('[初始化] 默认数据已创建')
