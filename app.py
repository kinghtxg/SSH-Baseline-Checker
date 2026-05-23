#!/usr/bin/env python3
"""
SSH 远程巡检工具 V4
- 真实交互式Shell体验
- 账号组批量巡检
- 左侧工具栏（telnet/ping/curl/SSH终端）
- 一个检查项多条命令，每条独立判断
"""
import os
import re
import json
import time
import subprocess
import socket as sk
from datetime import datetime

from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit

from models import (
    db, AccountGroup, TargetHost, ItemGroup, InspectionItem, ItemCommand,
    InspectionSession, InspectionResult, init_default_data
)
from ssh_engine import test_ssh, InteractiveShell, quick_exec, check_regex
from screenshot import generate_screenshot

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(BASE_DIR, "data", "inspector.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'connect_args': {'check_same_thread': False}}
app.config['JSON_AS_ASCII'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24).hex())

db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

with app.app_context():
    os.makedirs(os.path.join(BASE_DIR, 'data'), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'static', 'screenshots'), exist_ok=True)
    db.create_all()
    init_default_data()


# ==================== 全局 JSON 错误处理器 ====================

@app.errorhandler(404)
def api_not_found(e):
    resp = jsonify({'error': '接口不存在'})
    resp.status_code = 404
    return resp


@app.errorhandler(405)
def api_method_not_allowed(e):
    resp = jsonify({'error': '请求方法不允许'})
    resp.status_code = 405
    return resp


@app.errorhandler(500)
def api_server_error(e):
    resp = jsonify({'error': '服务器内部错误，请稍后重试'})
    resp.status_code = 500
    return resp


@app.errorhandler(Exception)
def api_unhandled_error(e):
    app.logger.error(f'API异常: {e}', exc_info=True)
    resp = jsonify({'error': f'请求处理异常: {str(e)}'})
    resp.status_code = 500
    return resp


# 存储活跃的交互式shell会话
active_shells = {}


# ==================== 页面路由 ====================

@app.route('/')
def index():
    groups = ItemGroup.query.order_by(ItemGroup.sort_order).all()
    account_groups = AccountGroup.query.order_by(AccountGroup.created_at.desc()).all()
    return render_template('index.html', groups=groups, account_groups=account_groups)


@app.route('/items')
def items_page():
    groups = ItemGroup.query.order_by(ItemGroup.sort_order).all()
    return render_template('items.html', groups=groups)


@app.route('/accounts')
def accounts_page():
    account_groups = AccountGroup.query.order_by(AccountGroup.created_at.desc()).all()
    return render_template('accounts.html', account_groups=account_groups)


@app.route('/reports')
def reports_page():
    sessions = InspectionSession.query.order_by(InspectionSession.created_at.desc()).all()
    return render_template('reports.html', sessions=sessions)


@app.route('/reports/<int:session_id>')
def report_detail(session_id):
    session = InspectionSession.query.get_or_404(session_id)
    results = InspectionResult.query.filter_by(session_id=session_id).order_by(InspectionResult.id).all()
    return render_template('report_detail.html', session=session, results=results)


@app.route('/terminal')
def terminal_page():
    """独立终端页面"""
    account_groups = AccountGroup.query.order_by(AccountGroup.created_at.desc()).all()
    return render_template('terminal.html', account_groups=account_groups)


@app.route('/inspect/single')
def single_inspect_page():
    """单账号检查页面"""
    groups = ItemGroup.query.order_by(ItemGroup.sort_order).all()
    return render_template('single_inspect.html', groups=groups)


@app.route('/api/inspect/single', methods=['POST'])
def single_inspect():
    """单账号检查API（即时模式，不保存账号）"""
    data = request.get_json()
    host = (data.get('host') or '').strip()
    port = int(data.get('port', 22))
    username = (data.get('username') or '').strip()
    password = data.get('password', '')
    can_sudo = bool(data.get('canSudo', False))
    root_password = data.get('rootPassword') or password
    group_ids = data.get('groupIds', [])

    if not host or not username or not password:
        return jsonify({'error': '主机、用户名和密码不能为空'}), 400

    # 查询检查项
    query = InspectionItem.query.filter_by(enabled=True)
    if group_ids:
        query = query.filter(InspectionItem.group_id.in_(group_ids))
    items = query.order_by(InspectionItem.sort_order).all()

    if not items:
        return jsonify({'error': '没有启用的检查项'}), 400

    total_cmds = sum(len(list(item.commands)) for item in items)
    if total_cmds == 0:
        return jsonify({'error': '没有命令'}), 400

    # 创建临时会话（不入库）
    session = InspectionSession(
        host=host, port=port, username=username,
        group_id=None, total_commands=total_cmds,
    )
    db.session.add(session)
    db.session.commit()

    return jsonify({
        'session': session.to_dict(),
        'items': [item.to_dict() for item in items],
    })


@app.route('/screenshots/<path:filename>')
def serve_screenshot(filename):
    return send_from_directory(os.path.join(BASE_DIR, 'static', 'screenshots'), filename)


# ==================== API: 账号组 ====================

@app.route('/api/account-groups', methods=['GET'])
def list_account_groups():
    groups = AccountGroup.query.order_by(AccountGroup.created_at.desc()).all()
    return jsonify({'data': [g.to_dict(include_hosts=True) for g in groups]})


@app.route('/api/account-groups', methods=['POST'])
def create_account_group():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': '名称不能为空'}), 400
    g = AccountGroup(name=name, description=(data.get('description') or '').strip() or None)
    db.session.add(g)
    db.session.commit()
    return jsonify({'data': g.to_dict()})


@app.route('/api/account-groups/<int:id>', methods=['PUT'])
def update_account_group(id):
    g = AccountGroup.query.get_or_404(id)
    data = request.get_json()
    if (data.get('name') or '').strip():
        g.name = data['name'].strip()
    g.description = data.get('description', g.description)
    db.session.commit()
    return jsonify({'data': g.to_dict()})


@app.route('/api/account-groups/<int:id>', methods=['DELETE'])
def delete_account_group(id):
    g = AccountGroup.query.get_or_404(id)
    db.session.delete(g)
    db.session.commit()
    return jsonify({'success': True})


# ==================== API: 目标主机 ====================

@app.route('/api/target-hosts', methods=['POST'])
def create_target_host():
    data = request.get_json()
    host = TargetHost(
        group_id=data.get('groupId'),
        name=(data.get('name') or '').strip() or None,
        host=(data.get('host') or '').strip(),
        port=int(data.get('port', 22)),
        username=(data.get('username') or '').strip(),
        password=data.get('password', ''),
        can_sudo=bool(data.get('canSudo', False)),
        root_password=data.get('rootPassword') or None,
        sort_order=0,
    )
    db.session.add(host)
    db.session.commit()
    return jsonify({'data': host.to_dict(hide_password=False)})


@app.route('/api/target-hosts/<int:id>', methods=['PUT'])
def update_target_host(id):
    h = TargetHost.query.get_or_404(id)
    data = request.get_json()
    for field in ['name', 'host', 'username', 'password', 'rootPassword']:
        if field in data:
            setattr(h, field, data[field] or None)
    if 'port' in data:
        h.port = int(data['port'])
    if 'canSudo' in data:
        h.can_sudo = bool(data['canSudo'])
    if 'groupId' in data:
        h.group_id = data['groupId']
    db.session.commit()
    return jsonify({'data': h.to_dict(hide_password=False)})


@app.route('/api/target-hosts/<int:id>', methods=['DELETE'])
def delete_target_host(id):
    h = TargetHost.query.get_or_404(id)
    db.session.delete(h)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/target-hosts/<int:id>/test', methods=['POST'])
def test_target_host(id):
    """测试目标主机SSH连接"""
    h = TargetHost.query.get_or_404(id)
    success, message = test_ssh(h.host, h.port, h.username, h.password)
    return jsonify({'success': success, 'message': message, 'host': h.host})


# ==================== API: 检查项分组 ====================

@app.route('/api/groups', methods=['GET'])
def list_groups():
    groups = ItemGroup.query.order_by(ItemGroup.sort_order).all()
    return jsonify({'data': [g.to_dict(include_items=True) for g in groups]})


@app.route('/api/groups', methods=['POST'])
def create_group():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': '名称不能为空'}), 400
    max_o = db.session.query(db.func.max(ItemGroup.sort_order)).scalar() or 0
    g = ItemGroup(name=name, description=(data.get('description') or '').strip() or None, sort_order=max_o + 10)
    db.session.add(g)
    db.session.commit()
    return jsonify({'data': g.to_dict()})


@app.route('/api/groups/<int:id>', methods=['PUT'])
def update_group(id):
    g = ItemGroup.query.get_or_404(id)
    data = request.get_json()
    if (data.get('name') or '').strip():
        g.name = data['name'].strip()
    g.description = data.get('description', g.description)
    db.session.commit()
    return jsonify({'data': g.to_dict()})


@app.route('/api/groups/<int:id>', methods=['DELETE'])
def delete_group(id):
    g = ItemGroup.query.get_or_404(id)
    db.session.delete(g)
    db.session.commit()
    return jsonify({'success': True})


# ==================== API: 检查项 ====================

@app.route('/api/items', methods=['POST'])
def create_item():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': '名称不能为空'}), 400
    cmds = data.get('commands', [])
    if not cmds:
        return jsonify({'error': '至少需要一条命令'}), 400

    max_o = db.session.query(db.func.max(InspectionItem.sort_order)).filter_by(group_id=data.get('groupId', 1)).scalar() or 0
    item = InspectionItem(
        group_id=data.get('groupId', 1), name=name,
        description=(data.get('description') or '').strip() or None,
        enabled=data.get('enabled', True), sort_order=max_o + 10,
    )
    db.session.add(item)
    db.session.flush()

    for i, c in enumerate(cmds):
        cmd = (c.get('command') or '').strip()
        if cmd:
            db.session.add(ItemCommand(
                item_id=item.id, command=cmd,
                success_regex=(c.get('successRegex') or '').strip() or None,
                description=(c.get('description') or '').strip() or None,
                require_root=bool(c.get('requireRoot', False)),
                sort_order=(i + 1) * 10,
            ))
    db.session.commit()
    return jsonify({'data': item.to_dict()})


@app.route('/api/items/<int:id>', methods=['GET'])
def get_item(id):
    item = InspectionItem.query.get_or_404(id)
    return jsonify({'data': item.to_dict()})


@app.route('/api/items/<int:id>', methods=['PUT'])
def update_item(id):
    item = InspectionItem.query.get_or_404(id)
    data = request.get_json()
    if 'name' in data:
        item.name = (data['name'] or '').strip()
    item.description = (data.get('description') or item.description or None)
    if 'enabled' in data:
        item.enabled = bool(data['enabled'])
    if 'groupId' in data:
        item.group_id = data['groupId']

    if 'commands' in data and isinstance(data['commands'], list):
        ItemCommand.query.filter_by(item_id=id).delete(synchronize_session=False)
        for i, c in enumerate(data['commands']):
            cmd = (c.get('command') or '').strip()
            if cmd:
                db.session.add(ItemCommand(
                    item_id=item.id, command=cmd,
                    success_regex=(c.get('successRegex') or '').strip() or None,
                    description=(c.get('description') or '').strip() or None,
                    require_root=bool(c.get('requireRoot', False)),
                    sort_order=(i + 1) * 10,
                ))
    db.session.commit()
    return jsonify({'data': item.to_dict()})


@app.route('/api/items/<int:id>', methods=['DELETE'])
def delete_item(id):
    item = InspectionItem.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/items/<int:id>/clone', methods=['POST'])
def clone_item(id):
    item = InspectionItem.query.get_or_404(id)
    clone = InspectionItem(
        group_id=item.group_id, name=f'{item.name} (副本)',
        description=item.description, enabled=item.enabled, sort_order=item.sort_order + 5,
    )
    db.session.add(clone)
    db.session.flush()
    for c in item.commands:
        db.session.add(ItemCommand(
            item_id=clone.id, command=c.command, success_regex=c.success_regex,
            description=c.description, sort_order=c.sort_order,
        ))
    db.session.commit()
    return jsonify({'data': clone.to_dict()})


@app.route('/api/items/bulk-delete', methods=['POST'])
def bulk_delete_items():
    data = request.get_json()
    ids = data.get('ids', [])
    if not ids:
        return jsonify({'error': '未选择'}), 400
    InspectionItem.query.filter(InspectionItem.id.in_(ids)).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({'success': True, 'deleted': len(ids)})


# ==================== API: 巡检 ====================

@app.route('/api/inspection/start', methods=['POST'])
def start_inspection():
    data = request.get_json()
    host = (data.get('host') or '').strip()
    port = int(data.get('port', 22))
    username = (data.get('username') or '').strip()
    password = data.get('password', '')
    group_id = data.get('groupId')

    if not host or not username or not password:
        return jsonify({'error': '主机、用户名和密码不能为空'}), 400

    query = InspectionItem.query.filter_by(enabled=True)
    if group_id:
        query = query.filter_by(group_id=group_id)
    items = query.order_by(InspectionItem.sort_order).all()

    if not items:
        return jsonify({'error': '没有启用的检查项'}), 400

    total_cmds = sum(len(list(item.commands)) for item in items)
    if total_cmds == 0:
        return jsonify({'error': '没有命令'}), 400

    session = InspectionSession(
        host=host, port=port, username=username,
        group_id=group_id, total_commands=total_cmds,
    )
    db.session.add(session)
    db.session.commit()

    return jsonify({
        'session': session.to_dict(),
        'items': [item.to_dict() for item in items],
    })


@app.route('/api/inspection/execute', methods=['POST'])
def execute_command():
    """执行单条命令（交互式shell + sudo提权）"""
    data = request.get_json()
    session_id = data.get('sessionId')
    item = data.get('item', {})
    command = data.get('command', {})

    host = data.get('host')
    port = data.get('port', 22)
    username = data.get('username')
    password = data.get('password')
    use_interactive = data.get('interactive', True)

    # Root提权参数
    can_sudo = bool(data.get('canSudo', False))
    root_password = data.get('rootPassword') or password
    root_state = data.get('rootState', {})  # 前端缓存的提权状态

    # 判断当前命令是否需要root权限
    needs_root = bool(command.get('requireRoot', False))

    # 去掉命令中的 sudo 前缀（su root 后不再需要 sudo）
    raw_cmd = (command.get('command') or '').strip()
    if raw_cmd.startswith('sudo '):
        raw_cmd = raw_cmd[5:].strip()

    try:
        if use_interactive:
            shell = InteractiveShell(host, port, username, password)
            shell.connect()
            prompt = shell.prompt

            if needs_root and can_sudo:
                # 检查是否已提权（前端缓存的root状态）
                if root_state.get('isActive'):
                    # 已提权，直接在已提权shell中执行命令
                    # 先原地提权验证状态
                    switch_res = shell.su_switch(root_password, timeout=10)
                    if switch_res['success']:
                        result = shell.exec_command(raw_cmd, timeout=30)
                        prompt = shell.prompt
                    else:
                        result = switch_res
                        result['exitCode'] = -1
                        result['output'] = f"[su root 提权失败] {switch_res.get('reason', '')}\n{switch_res.get('output', '')}"
                else:
                    # 首次提权
                    result = shell.execute_as_root(raw_cmd, root_password, timeout=30)
                    prompt = shell.prompt
            else:
                result = shell.exec_command(raw_cmd, timeout=30)

            shell.close()
        else:
            result = quick_exec(host, port, username, password, raw_cmd, timeout=30)
            prompt = f'[{username}@{host}]$'

        regex_matched = check_regex(result['output'], command.get('successRegex'))

        screenshot_path = generate_screenshot(
            cmd_index=data.get('index', 1), total=data.get('total', 1),
            host_info=f"{username}@{host}", command=raw_cmd,
            output=result['output'] if isinstance(result.get('output'), str) else '',
            exit_code=result.get('exitCode', -1),
            regex=command.get('successRegex'), regex_matched=regex_matched,
            duration=result.get('duration', 0), prompt=prompt,
        )

        db_result = InspectionResult(
            session_id=session_id, item_id=item.get('id'), command_id=command.get('id'),
            item_name=item.get('name'), command_text=command['command'],
            command_desc=command.get('description'),
            output=(result['output'][:5000] if result.get('output') and isinstance(result['output'], str) else None),
            success_regex=command.get('successRegex'),
            regex_matched=regex_matched, exit_code=result.get('exitCode', -1),
            executed=True, screenshot_path=screenshot_path, duration=result.get('duration', 0),
        )
        db.session.add(db_result)
        db.session.commit()

        return jsonify({
            'exitCode': result.get('exitCode', -1),
            'output': (result['output'][:2000] if result.get('output') and isinstance(result['output'], str) else ''),
            'regexMatched': regex_matched,
            'screenshotPath': screenshot_path,
            'duration': result.get('duration', 0),
            'prompt': prompt,
            'rootActive': bool(needs_root and can_sudo),
        })

    except Exception as e:
        return jsonify({'error': str(e), 'exitCode': -1}), 500


@app.route('/api/inspection/finish', methods=['POST'])
def finish_session():
    data = request.get_json()
    session = InspectionSession.query.get(data.get('sessionId'))
    if not session:
        return jsonify({'error': '会话不存在'}), 404
    session.status = 'completed'
    session.success_count = data.get('successCount', 0)
    session.fail_count = data.get('failCount', 0)
    session.duration = data.get('duration', 0)
    db.session.commit()
    return jsonify({'data': session.to_dict()})


@app.route('/api/inspect/single/test', methods=['POST'])
def test_single_connection():
    """测试单账号SSH连接"""
    data = request.get_json()
    host = (data.get('host') or '').strip()
    port = int(data.get('port', 22))
    username = (data.get('username') or '').strip()
    password = data.get('password', '')

    if not host or not username or not password:
        return jsonify({'success': False, 'message': '请填写完整信息'})

    success, message = test_ssh(host, port, username, password)
    # 如果连接成功且启用提权，尝试验证su root权限
    can_sudo = bool(data.get('canSudo', False))
    su_msg = ''
    if success and can_sudo:
        root_password = data.get('rootPassword') or password
        try:
            shell = InteractiveShell(host, port, username, password)
            shell.connect()
            switch_res = shell.su_switch(root_password, timeout=10)
            shell.close()
            if switch_res['success']:
                su_msg = ' | su root 提权成功'
            else:
                su_msg = f' | su root 提权失败: {switch_res.get("reason", "未知")}'
        except Exception:
            su_msg = ' | su 验证异常'

    return jsonify({
        'success': success,
        'message': message + su_msg,
        'host': host,
    })


@app.route('/api/inspection/batch/start', methods=['POST'])
def start_batch_inspection():
    """批量巡检：遍历账号组内所有主机"""
    data = request.get_json()
    group_id = int(data.get('groupId', 0))

    if not group_id:
        return jsonify({'error': '请选择账号组'}), 400

    account_group = AccountGroup.query.get(group_id)
    if not account_group:
        return jsonify({'error': '账号组不存在'}), 404

    hosts = TargetHost.query.filter_by(group_id=group_id).order_by(TargetHost.sort_order).all()
    if not hosts:
        return jsonify({'error': '该账号组下没有主机'}), 400

    # 查询检查项
    item_group_id = data.get('itemGroupId')
    query = InspectionItem.query.filter_by(enabled=True)
    if item_group_id:
        query = query.filter_by(group_id=int(item_group_id))
    items = query.order_by(InspectionItem.sort_order).all()

    if not items:
        return jsonify({'error': '没有启用的检查项'}), 400

    total_cmds = sum(len(list(item.commands)) for item in items)
    if total_cmds == 0:
        return jsonify({'error': '没有命令'}), 400

    return jsonify({
        'groupName': account_group.name,
        'hosts': [h.to_dict(hide_password=False) for h in hosts],
        'items': [item.to_dict() for item in items],
        'totalCommands': total_cmds,
    })


# ==================== API: 报告 ====================

@app.route('/api/sessions', methods=['GET'])
def list_sessions():
    sessions = InspectionSession.query.order_by(InspectionSession.created_at.desc()).all()
    return jsonify({'data': [s.to_dict() for s in sessions]})


@app.route('/api/sessions/<int:id>', methods=['GET'])
def get_session(id):
    session = InspectionSession.query.get_or_404(id)
    results = InspectionResult.query.filter_by(session_id=id).order_by(InspectionResult.id).all()
    return jsonify({'session': session.to_dict(), 'results': [r.to_dict() for r in results]})


@app.route('/api/sessions/<int:id>', methods=['DELETE'])
def delete_session(id):
    session = InspectionSession.query.get_or_404(id)
    db.session.delete(session)
    db.session.commit()
    return jsonify({'success': True})


# ==================== API: 工具 ====================

@app.route('/api/tools/ping', methods=['POST'])
def tool_ping():
    """Ping检测"""
    data = request.get_json()
    target = (data.get('target') or '').strip()
    if not target:
        return jsonify({'error': '请输入目标'}), 400
    try:
        import platform
        if platform.system() == 'Windows':
            result = subprocess.run(
                ['ping', '-n', '4', '-w', '2000', target],
                capture_output=True, text=True, timeout=15
            )
            cmd_display = f'ping -n 4 {target}'
        else:
            result = subprocess.run(
                ['ping', '-c', '4', '-W', '2', target],
                capture_output=True, text=True, timeout=15
            )
            cmd_display = f'ping -c 4 {target}'
        return jsonify({
            'success': result.returncode == 0,
            'output': result.stdout + result.stderr,
            'command': cmd_display,
        })
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'output': '超时', 'command': f'ping {target}'})
    except Exception as e:
        return jsonify({'success': False, 'output': str(e), 'command': f'ping {target}'})


@app.route('/api/tools/telnet', methods=['POST'])
def tool_telnet():
    """Telnet端口检测"""
    data = request.get_json()
    host = (data.get('host') or '').strip()
    port = int(data.get('port', 23))
    if not host:
        return jsonify({'error': '请输入主机'}), 400
    try:
        sock = sk.socket(sk.AF_INET, sk.SOCK_STREAM)
        sock.settimeout(5)
        start = time.time()
        result = sock.connect_ex((host, port))
        elapsed = (time.time() - start) * 1000
        sock.close()
        if result == 0:
            return jsonify({'success': True, 'output': f'{host}:{port} 端口开放 (耗时 {elapsed:.1f}ms)', 'command': f'telnet {host} {port}'})
        else:
            return jsonify({'success': False, 'output': f'{host}:{port} 端口关闭或不可达 (错误码 {result})', 'command': f'telnet {host} {port}'})
    except Exception as e:
        return jsonify({'success': False, 'output': str(e), 'command': f'telnet {host} {port}'})


@app.route('/api/tools/curl', methods=['POST'])
def tool_curl():
    """CURL检测"""
    data = request.get_json()
    url = (data.get('url') or '').strip()
    if not url:
        return jsonify({'error': '请输入URL'}), 400
    if not url.startswith('http'):
        url = 'http://' + url
    try:
        result = subprocess.run(
            ['curl', '-s', '-o', '/dev/null', '-w',
             'HTTP_CODE: %{http_code}\nTIME: %{time_total}s\nSIZE: %{size_download}b',
             '-L', '--max-time', '10', url],
            capture_output=True, text=True, timeout=15
        )
        output = result.stdout + ('\n' + result.stderr if result.stderr else '')
        http_code = re.search(r'HTTP_CODE:\s*(\d+)', output)
        code = http_code.group(1) if http_code else '???'
        success = code.startswith('2') or code.startswith('3')
        return jsonify({'success': success, 'output': output, 'command': f'curl -I {url}', 'httpCode': code})
    except Exception as e:
        return jsonify({'success': False, 'output': str(e), 'command': f'curl {url}'})


@app.route('/api/regex-test', methods=['POST'])
def regex_test():
    data = request.get_json()
    pattern = data.get('pattern', '')
    text = data.get('text', '')
    if not pattern:
        return jsonify({'matched': None, 'message': '正则表达式为空'})
    try:
        matched = bool(re.search(pattern, text, re.MULTILINE))
        return jsonify({'matched': matched})
    except re.error as e:
        return jsonify({'matched': None, 'message': f'正则语法错误: {str(e)}'})


# ==================== WebSocket: SSH终端 ====================

@socketio.on('ssh_connect')
def handle_ssh_connect(data):
    """连接SSH交互式终端"""
    sid = request.sid
    host = data.get('host')
    port = int(data.get('port', 22))
    username = data.get('username')
    password = data.get('password')

    try:
        shell = InteractiveShell(host, port, username, password)
        shell.connect()
        active_shells[sid] = shell

        # 发送初始输出
        initial = ''
        for _ in range(20):
            chunk = shell.get_output(0.2)
            if not chunk:
                break
            initial += chunk

        emit('ssh_data', {'output': initial, 'prompt': shell.prompt})
    except Exception as e:
        emit('ssh_error', {'message': str(e)})


@socketio.on('ssh_send')
def handle_ssh_send(data):
    """发送命令到SSH终端"""
    sid = request.sid
    shell = active_shells.get(sid)
    if not shell or not shell.connected:
        emit('ssh_error', {'message': '未连接'})
        return

    cmd = data.get('command', '')
    shell.send(cmd)

    # 收集输出
    output = ''
    for _ in range(30):
        chunk = shell.get_output(0.3)
        if not chunk:
            break
        output += chunk

    emit('ssh_data', {'output': output, 'prompt': shell.prompt})


@socketio.on('ssh_resize')
def handle_ssh_resize(data):
    """调整终端大小"""
    sid = request.sid
    shell = active_shells.get(sid)
    if shell and shell.chan:
        shell.chan.resize_pty(
            width=data.get('cols', 120),
            height=data.get('rows', 40)
        )


@socketio.on('disconnect')
def handle_disconnect():
    """断开连接时清理"""
    sid = request.sid
    shell = active_shells.pop(sid, None)
    if shell:
        shell.close()


# ==================== 启动 ====================

if __name__ == '__main__':
    print('=' * 50)
    print('SSH 远程巡检工具 V4')
    print('功能: 交互式Shell | 账号组 | 工具栏')
    print('=' * 50)
    print('访问: http://localhost:38800')
    print('=' * 50)
    socketio.run(app, host='0.0.0.0', port=38800, debug=False, allow_unsafe_werkzeug=True)
