"""
数据库模型单元测试 - 测试所有模型的 CRUD、关联查询、默认数据初始化
"""
import pytest
from datetime import datetime
from app import app, db
from models import (
    AccountGroup, TargetHost, ItemGroup, InspectionItem, ItemCommand,
    InspectionSession, InspectionResult, init_default_data
)


@pytest.fixture
def test_db():
    """创建独立测试数据库"""
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['TESTING'] = True
    with app.app_context():
        db.create_all()
        yield db
        db.session.remove()
        db.drop_all()


class TestAccountGroup:
    """测试 AccountGroup 模型"""

    def test_create(self, test_db):
        group = AccountGroup(name='测试组', description='测试描述')
        db.session.add(group)
        db.session.commit()
        assert group.id is not None
        assert group.name == '测试组'
        assert isinstance(group.created_at, datetime)

    def test_to_dict(self, test_db):
        group = AccountGroup(name='序列化测试')
        db.session.add(group)
        db.session.commit()
        d = group.to_dict()
        assert d['name'] == '序列化测试'
        assert 'createdAt' in d

    def test_to_dict_include_hosts(self, test_db):
        group = AccountGroup(name='含主机组')
        db.session.add(group)
        db.session.flush()
        host = TargetHost(group_id=group.id, name='主机1', host='192.168.1.1',
                          username='root', password='pass123')
        db.session.add(host)
        db.session.commit()
        d = group.to_dict(include_hosts=True)
        assert len(d['hosts']) == 1
        assert d['hosts'][0]['name'] == '主机1'

    def test_update(self, test_db):
        group = AccountGroup(name='旧名称')
        db.session.add(group)
        db.session.commit()
        group.name = '新名称'
        db.session.commit()
        updated = db.session.get(AccountGroup, group.id)
        assert updated.name == '新名称'

    def test_delete(self, test_db):
        group = AccountGroup(name='待删除')
        db.session.add(group)
        db.session.commit()
        gid = group.id
        db.session.delete(group)
        db.session.commit()
        assert db.session.get(AccountGroup, gid) is None

    def test_cascade_delete_hosts(self, test_db):
        group = AccountGroup(name='级联删除测试')
        db.session.add(group)
        db.session.flush()
        host = TargetHost(group_id=group.id, name='主机', host='10.0.0.1',
                          username='admin', password='pass')
        db.session.add(host)
        db.session.commit()
        hid = host.id
        db.session.delete(group)
        db.session.commit()
        assert db.session.get(TargetHost, hid) is None


class TestTargetHost:
    """测试 TargetHost 模型"""

    def test_create(self, test_db):
        group = AccountGroup(name='测试组')
        db.session.add(group)
        db.session.flush()
        host = TargetHost(group_id=group.id, name='生产服务器', host='192.168.1.100',
                          port=2222, username='admin', password='secret',
                          can_sudo=True, root_password='root_secret')
        db.session.add(host)
        db.session.commit()
        assert host.host == '192.168.1.100'
        assert host.port == 2222

    def test_to_dict_hide_password(self, test_db):
        group = AccountGroup(name='测试组')
        db.session.add(group)
        db.session.flush()
        host = TargetHost(group_id=group.id, name='主机', host='10.0.0.1',
                          username='user', password='mypass', root_password='rootpass')
        db.session.add(host)
        db.session.commit()
        d = host.to_dict(hide_password=True)
        assert 'password' not in d
        assert 'rootPassword' not in d

    def test_to_dict_show_password(self, test_db):
        group = AccountGroup(name='测试组')
        db.session.add(group)
        db.session.flush()
        host = TargetHost(group_id=group.id, name='主机', host='10.0.0.1',
                          username='user', password='mypass', root_password='rootpass')
        db.session.add(host)
        db.session.commit()
        d = host.to_dict(hide_password=False)
        assert d['password'] == 'mypass'

    def test_default_port(self, test_db):
        group = AccountGroup(name='测试组')
        db.session.add(group)
        db.session.flush()
        host = TargetHost(group_id=group.id, name='主机', host='10.0.0.1',
                          username='user', password='pass')
        db.session.add(host)
        db.session.commit()
        assert host.port == 22

    def test_backref(self, test_db):
        group = AccountGroup(name='测试组')
        db.session.add(group)
        db.session.flush()
        host = TargetHost(group_id=group.id, name='主机', host='10.0.0.1',
                          username='user', password='pass')
        db.session.add(host)
        db.session.commit()
        assert host.account_group.name == '测试组'


class TestItemGroup:
    """测试 ItemGroup 模型"""

    def test_create(self, test_db):
        ig = ItemGroup(name='系统安全', description='系统安全相关检查', sort_order=1)
        db.session.add(ig)
        db.session.commit()
        assert ig.name == '系统安全'

    def test_to_dict(self, test_db):
        ig = ItemGroup(name='网络检查')
        db.session.add(ig)
        db.session.commit()
        d = ig.to_dict()
        assert d['name'] == '网络检查'

    def test_to_dict_include_items(self, test_db):
        ig = ItemGroup(name='安全组')
        db.session.add(ig)
        db.session.flush()
        item = InspectionItem(group_id=ig.id, name='检查SSH配置', description='检查SSH配置',
                              sort_order=1)
        db.session.add(item)
        db.session.commit()
        d = ig.to_dict(include_items=True)
        assert len(d['items']) == 1


class TestInspectionItem:
    """测试 InspectionItem 模型"""

    def test_create_with_commands(self, test_db):
        ig = ItemGroup(name='安全组')
        db.session.add(ig)
        db.session.flush()
        item = InspectionItem(group_id=ig.id, name='SSH配置检查', description='检查SSH配置',
                              sort_order=1)
        db.session.add(item)
        db.session.flush()
        cmd = ItemCommand(item_id=item.id, command='cat /etc/ssh/sshd_config',
                          success_regex=r'PermitRootLogin no', description='检查Root登录',
                          require_root=True)
        db.session.add(cmd)
        db.session.commit()
        assert len(item.commands) == 1
        assert item.commands[0].command == 'cat /etc/ssh/sshd_config'
        assert item.commands[0].require_root is True

    def test_default_enabled(self, test_db):
        ig = ItemGroup(name='测试组')
        db.session.add(ig)
        db.session.flush()
        item = InspectionItem(group_id=ig.id, name='测试项', description='测试')
        db.session.add(item)
        db.session.commit()
        assert item.enabled is True

    def test_require_root_on_command(self, test_db):
        """require_root 字段在 ItemCommand 上"""
        ig = ItemGroup(name='测试组')
        db.session.add(ig)
        db.session.flush()
        item = InspectionItem(group_id=ig.id, name='Root检查', description='需要Root')
        db.session.add(item)
        db.session.flush()
        cmd = ItemCommand(item_id=item.id, command='cat /etc/shadow',
                          description='检查shadow', require_root=True)
        db.session.add(cmd)
        db.session.commit()
        assert cmd.require_root is True

    def test_cascade_delete_commands(self, test_db):
        ig = ItemGroup(name='测试组')
        db.session.add(ig)
        db.session.flush()
        item = InspectionItem(group_id=ig.id, name='测试项', description='测试')
        db.session.add(item)
        db.session.flush()
        cmd = ItemCommand(item_id=item.id, command='ls', description='列表')
        db.session.add(cmd)
        db.session.commit()
        cid = cmd.id
        db.session.delete(item)
        db.session.commit()
        assert db.session.get(ItemCommand, cid) is None


class TestInspectionSession:
    """测试 InspectionSession 模型"""

    def test_create(self, test_db):
        session = InspectionSession(
            host='192.168.1.1', port=22, username='admin',
            status='running'
        )
        db.session.add(session)
        db.session.commit()
        assert session.status == 'running'
        assert isinstance(session.created_at, datetime)

    def test_status_transition(self, test_db):
        session = InspectionSession(
            host='192.168.1.1', port=22, username='admin',
            status='running'
        )
        db.session.add(session)
        db.session.commit()
        session.status = 'completed'
        db.session.commit()
        updated = db.session.get(InspectionSession, session.id)
        assert updated.status == 'completed'


class TestInspectionResult:
    """测试 InspectionResult 模型"""

    def test_create(self, test_db):
        ig = ItemGroup(name='测试组')
        db.session.add(ig)
        db.session.flush()
        item = InspectionItem(group_id=ig.id, name='SSH检查', description='检查SSH')
        db.session.add(item)
        db.session.flush()
        cmd = ItemCommand(item_id=item.id, command='cat /etc/ssh/sshd_config',
                          success_regex=r'PermitRootLogin no')
        db.session.add(cmd)
        db.session.flush()
        session = InspectionSession(
            host='192.168.1.1', port=22, username='admin',
            status='running'
        )
        db.session.add(session)
        db.session.flush()

        result = InspectionResult(
            session_id=session.id,
            item_id=item.id,
            command_id=cmd.id,
            item_name='SSH检查',
            command_text='cat /etc/ssh/sshd_config',
            output='PermitRootLogin no',
            exit_code=0,
            success_regex=r'PermitRootLogin no',
            regex_matched=True,
            executed=True
        )
        db.session.add(result)
        db.session.commit()
        assert result.regex_matched is True

    def test_relation(self, test_db):
        session = InspectionSession(
            host='192.168.1.1', port=22, username='admin',
            status='completed'
        )
        db.session.add(session)
        db.session.flush()
        for i in range(3):
            result = InspectionResult(
                session_id=session.id,
                item_name=f'检查项{i}',
                command_text=f'cmd{i}',
                exit_code=0,
                executed=True
            )
            db.session.add(result)
        db.session.commit()
        results = InspectionResult.query.filter_by(session_id=session.id).all()
        assert len(results) == 3
        assert len(session.results) == 3


class TestInitDefaultData:
    """测试默认数据初始化"""

    def test_init(self, test_db):
        init_default_data()
        groups = AccountGroup.query.all()
        assert len(groups) >= 1
        assert any(g.name == '默认测试组' for g in groups)

    def test_idempotent(self, test_db):
        init_default_data()
        count_before = AccountGroup.query.count()
        init_default_data()
        count_after = AccountGroup.query.count()
        assert count_before == count_after