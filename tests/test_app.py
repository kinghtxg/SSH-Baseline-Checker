"""
数据库模型单元测试 - 所有模型CRUD、关联查询、默认数据初始化
"""
import os
import pytest
from datetime import datetime

# 为测试创建独立的数据库
os.environ.setdefault('DB_PATH', ':memory:')

from app import app, db
from models import (
    AccountGroup, TargetHost, ItemGroup, InspectionItem,
    ItemCommand, InspectionSession, InspectionResult,
    init_default_data
)


@pytest.fixture
def test_app():
    """创建测试Flask应用"""
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(test_app):
    """创建测试客户端"""
    return test_app.test_client()


@pytest.fixture
def app_context(test_app):
    """创建应用上下文"""
    with test_app.app_context():
        db.create_all()
        yield
        db.session.rollback()
        db.drop_all()


class TestAccountGroup:
    """测试 AccountGroup 模型"""
    
    def test_create(self, test_app):
        """测试创建账号组"""
        with test_app.app_context():
            db.create_all()
            group = AccountGroup(name='测试组', description='测试描述')
            db.session.add(group)
            db.session.commit()
            
            assert group.id is not None
            assert group.name == '测试组'
            assert group.description == '测试描述'
            assert group.created_at is not None
    
    def test_to_dict(self, test_app):
        """测试序列化"""
        with test_app.app_context():
            db.create_all()
            group = AccountGroup(name='生产组', description='生产环境服务器')
            db.session.add(group)
            db.session.commit()
            
            d = group.to_dict()
            assert d['name'] == '生产组'
            assert d['description'] == '生产环境服务器'
            assert 'createdAt' in d
    
    def test_to_dict_with_hosts(self, test_app):
        """测试包含主机的序列化"""
        with test_app.app_context():
            db.create_all()
            group = AccountGroup(name='测试组', description='测试')
            db.session.add(group)
            db.session.flush()
            
            host = TargetHost(group_id=group.id, name='web01', host='10.0.0.1',
                              port=22, username='admin', password='pass')
            db.session.add(host)
            db.session.commit()
            
            d = group.to_dict(include_hosts=True)
            assert 'hosts' in d
            assert len(d['hosts']) == 1
            assert d['hosts'][0]['host'] == '10.0.0.1'
    
    def test_update(self, test_app):
        """测试更新账号组"""
        with test_app.app_context():
            db.create_all()
            group = AccountGroup(name='旧名称')
            db.session.add(group)
            db.session.commit()
            
            group.name = '新名称'
            group.description = '新描述'
            db.session.commit()
            
            updated = AccountGroup.query.get(group.id)
            assert updated.name == '新名称'
            assert updated.description == '新描述'
    
    def test_delete(self, test_app):
        """测试删除账号组"""
        with test_app.app_context():
            db.create_all()
            group = AccountGroup(name='待删除')
            db.session.add(group)
            db.session.commit()
            
            gid = group.id
            db.session.delete(group)
            db.session.commit()
            
            assert AccountGroup.query.get(gid) is None
    
    def test_cascade_delete_hosts(self, test_app):
        """测试级联删除主机"""
        with test_app.app_context():
            db.create_all()
            group = AccountGroup(name='父组')
            db.session.add(group)
            db.session.flush()
            
            host = TargetHost(group_id=group.id, host='10.0.0.1', port=22,
                              username='user', password='pass')
            db.session.add(host)
            db.session.commit()
            
            gid = group.id
            hid = host.id
            db.session.delete(group)
            db.session.commit()
            
            assert AccountGroup.query.get(gid) is None
            assert TargetHost.query.get(hid) is None  # 级联删除


class TestTargetHost:
    """测试 TargetHost 模型"""
    
    @pytest.fixture
    def setup_group(self, test_app):
        with test_app.app_context():
            db.create_all()
            group = AccountGroup(name='测试组')
            db.session.add(group)
            db.session.commit()
            return group.id
    
    def test_create(self, test_app):
        """测试创建目标主机"""
        with test_app.app_context():
            db.create_all()
            group = AccountGroup(name='组')
            db.session.add(group)
            db.session.flush()
            
            host = TargetHost(
                group_id=group.id, name='生产服务器01', host='192.168.1.100',
                port=22, username='root', password='secret',
                can_sudo=True, root_password='rootpass', sort_order=10
            )
            db.session.add(host)
            db.session.commit()
            
            assert host.id is not None
            assert host.host == '192.168.1.100'
            assert host.username == 'root'
            assert host.can_sudo is True
    
    def test_to_dict_hide_password(self, test_app):
        """测试序列化隐藏密码"""
        with test_app.app_context():
            db.create_all()
            group = AccountGroup(name='组')
            db.session.add(group)
            db.session.flush()
            
            host = TargetHost(group_id=group.id, host='10.0.0.1', port=22,
                              username='admin', password='secret123',
                              can_sudo=False)
            db.session.add(host)
            db.session.commit()
            
            d = host.to_dict()
            assert 'password' not in d
            assert d['host'] == '10.0.0.1'
            assert d['canSudo'] is False
    
    def test_to_dict_show_password(self, test_app):
        """测试序列化显示密码"""
        with test_app.app_context():
            db.create_all()
            group = AccountGroup(name='组')
            db.session.add(group)
            db.session.flush()
            
            host = TargetHost(group_id=group.id, host='10.0.0.1', port=22,
                              username='admin', password='secret123',
                              root_password='rootpass')
            db.session.add(host)
            db.session.commit()
            
            d = host.to_dict(hide_password=False)
            assert d['password'] == 'secret123'
            assert d['rootPassword'] == 'rootpass'
    
    def test_default_port(self, test_app):
        """测试默认端口22"""
        with test_app.app_context():
            db.create_all()
            group = AccountGroup(name='组')
            db.session.add(group)
            db.session.flush()
            
            host = TargetHost(group_id=group.id, host='10.0.0.1', username='user',
                              password='pass')
            db.session.add(host)
            db.session.commit()
            
            assert host.port == 22
    
    def test_backref(self, test_app):
        """测试反向引用"""
        with test_app.app_context():
            db.create_all()
            group = AccountGroup(name='组')
            db.session.add(group)
            db.session.flush()
            
            host = TargetHost(group_id=group.id, host='10.0.0.1', username='user',
                              password='pass')
            db.session.add(host)
            db.session.commit()
            
            # 反向引用
            assert host.account_group.id == group.id
            assert host.account_group.name == '组'


class TestItemGroup:
    """测试 ItemGroup 模型"""
    
    def test_create(self, test_app):
        with test_app.app_context():
            db.create_all()
            ig = ItemGroup(name='系统安全', description='安全检查项', sort_order=10)
            db.session.add(ig)
            db.session.commit()
            
            assert ig.id is not None
            assert ig.name == '系统安全'
    
    def test_to_dict_with_items(self, test_app):
        with test_app.app_context():
            db.create_all()
            ig = ItemGroup(name='安全')
            db.session.add(ig)
            db.session.flush()
            
            item = InspectionItem(group_id=ig.id, name='检查项1', sort_order=10)
            db.session.add(item)
            db.session.commit()
            
            d = ig.to_dict(include_items=True)
            assert len(d['items']) == 1
            assert d['items'][0]['name'] == '检查项1'


class TestInspectionItem:
    """测试 InspectionItem 模型"""
    
    def test_create_with_commands(self, test_app):
        with test_app.app_context():
            db.create_all()
            ig = ItemGroup(name='安全')
            db.session.add(ig)
            db.session.flush()
            
            item = InspectionItem(group_id=ig.id, name='防火墙检查',
                                  description='检查防火墙', enabled=True, sort_order=30)
            db.session.add(item)
            db.session.flush()
            
            cmd1 = ItemCommand(item_id=item.id, command='iptables -L',
                               success_regex=r'Chain INPUT', description='iptables规则',
                               require_root=True, sort_order=10)
            cmd2 = ItemCommand(item_id=item.id, command='systemctl status firewalld',
                               success_regex=r'Active:', description='firewalld状态',
                               require_root=False, sort_order=20)
            db.session.add(cmd1)
            db.session.add(cmd2)
            db.session.commit()
            
            d = item.to_dict(include_commands=True)
            assert len(d['commands']) == 2
            assert d['commands'][0]['requireRoot'] is True
            assert d['commands'][1]['requireRoot'] is False
    
    def test_enabled_default(self, test_app):
        with test_app.app_context():
            db.create_all()
            ig = ItemGroup(name='安全')
            db.session.add(ig)
            db.session.flush()
            
            item = InspectionItem(group_id=ig.id, name='测试')
            db.session.add(item)
            db.session.commit()
            
            assert item.enabled is True
    
    def test_require_root_field(self, test_app):
        """测试 require_root 字段"""
        with test_app.app_context():
            db.create_all()
            ig = ItemGroup(name='安全')
            db.session.add(ig)
            db.session.flush()
            
            item = InspectionItem(group_id=ig.id, name='root检查')
            db.session.add(item)
            db.session.flush()
            
            cmd = ItemCommand(item_id=item.id, command='cat /etc/shadow',
                              require_root=True)
            db.session.add(cmd)
            db.session.commit()
            
            d = item.to_dict()
            assert d['commands'][0]['requireRoot'] is True
    
    def test_cascade_delete_commands(self, test_app):
        with test_app.app_context():
            db.create_all()
            ig = ItemGroup(name='安全')
            db.session.add(ig)
            db.session.flush()
            
            item = InspectionItem(group_id=ig.id, name='检查项')
            db.session.add(item)
            db.session.flush()
            
            cmd = ItemCommand(item_id=item.id, command='ls')
            db.session.add(cmd)
            db.session.commit()
            
            cid = cmd.id
            db.session.delete(item)
            db.session.commit()
            
            assert ItemCommand.query.get(cid) is None


class TestInspectionSession:
    """测试 InspectionSession 模型"""
    
    def test_create(self, test_app):
        with test_app.app_context():
            db.create_all()
            session = InspectionSession(
                host='192.168.1.1', port=22, username='admin',
                total_commands=10, success_count=8, fail_count=2,
                duration=35.5, status='completed'
            )
            db.session.add(session)
            db.session.commit()
            
            assert session.id is not None
            d = session.to_dict()
            assert d['host'] == '192.168.1.1'
            assert d['totalCommands'] == 10
            assert d['successCount'] == 8
            assert d['failCount'] == 2
            assert d['duration'] == 35.5
            assert d['status'] == 'completed'
    
    def test_default_status(self, test_app):
        with test_app.app_context():
            db.create_all()
            session = InspectionSession(
                host='10.0.0.1', port=22, username='user',
                total_commands=5
            )
            db.session.add(session)
            db.session.commit()
            
            assert session.status == 'running'
            assert session.success_count == 0
            assert session.fail_count == 0


class TestInspectionResult:
    """测试 InspectionResult 模型"""
    
    def test_create(self, test_app):
        with test_app.app_context():
            db.create_all()
            session = InspectionSession(
                host='192.168.1.1', port=22, username='admin',
                total_commands=5
            )
            db.session.add(session)
            db.session.flush()
            
            result = InspectionResult(
                session_id=session.id, item_id=1, command_id=1,
                item_name='防火墙检查', command_text='iptables -L',
                command_desc='iptables规则', output='Chain INPUT...',
                success_regex=r'Chain INPUT', regex_matched=True,
                exit_code=0, executed=True,
                screenshot_path='/screenshots/cmd_1_123_iptables.png',
                duration=1.5
            )
            db.session.add(result)
            db.session.commit()
            
            d = result.to_dict()
            assert d['itemName'] == '防火墙检查'
            assert d['regexMatched'] is True
            assert d['exitCode'] == 0
            assert d['executed'] is True
            assert 'screenshotPath' in d
    
    def test_associated_query(self, test_app):
        """测试关联查询"""
        with test_app.app_context():
            db.create_all()
            session = InspectionSession(
                host='10.0.0.1', port=22, username='admin',
                total_commands=3
            )
            db.session.add(session)
            db.session.flush()
            
            for i in range(3):
                result = InspectionResult(
                    session_id=session.id, item_name=f'检查项{i}',
                    command_text=f'cmd{i}', exit_code=0, executed=True
                )
                db.session.add(result)
            db.session.commit()
            
            results = InspectionResult.query.filter_by(session_id=session.id).all()
            assert len(results) == 3
            
            # 通过 session 反向访问
            assert len(session.results) == 3


class TestInitDefaultData:
    """测试默认数据初始化"""
    
    def test_init(self, test_app):
        with test_app.app_context():
            db.create_all()
            init_default_data()
            
            # 应该有默认账号组
            groups = AccountGroup.query.all()
            assert len(groups) >= 1
            assert any(g.name == '默认测试组' for g in groups)
            
            # 应该有默认检查项分组
            igs = ItemGroup.query.all()
            assert len(igs) >= 1
            assert any(ig.name == '系统安全巡检' for ig in igs)
            
            # 应该有检查项
            items = InspectionItem.query.all()
            assert len(items) >= 3  # 至少3个检查项
            
            # check require_root field exists
            cmd = ItemCommand.query.filter_by(require_root=False).first()
            assert cmd is not None
            
            # 幂等性测试
            init_default_data()
            groups2 = AccountGroup.query.all()
            assert len(groups2) >= 1
    
    def test_idempotent(self, test_app):
        """测试幂等性：多次调用不重复创建"""
        with test_app.app_context():
            db.create_all()
            init_default_data()
            first_count = ItemGroup.query.count()
            
            init_default_data()
            assert ItemGroup.query.count() == first_count