"""
SSH 引擎 - 交互式Shell + 巡检执行 + Root提权
使用 paramiko invoke_shell 获取真实shell体验
"""
import re
import time
import socket
import threading
import paramiko
from queue import Queue, Empty


def test_ssh(host, port, username, password, timeout=10):
    """测试SSH连接"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(hostname=host, port=port, username=username, password=password,
                       timeout=timeout, banner_timeout=timeout, auth_timeout=timeout,
                       look_for_keys=False, allow_agent=False)
        return True, '连接成功'
    except paramiko.AuthenticationException:
        return False, '认证失败：用户名或密码错误'
    except socket.timeout:
        return False, '连接超时'
    except socket.error as e:
        return False, f'网络错误：{str(e)}'
    except Exception as e:
        return False, f'连接失败：{str(e)}'
    finally:
        client.close()


class InteractiveShell:
    """交互式SSH Shell - 获取真实终端体验，支持su root提权"""

    def __init__(self, host, port, username, password):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client = None
        self.chan = None
        self.prompt = ''
        self.connected = False
        self.is_root = False       # 是否已提权到root
        self.root_verified = False # 是否已验证过root状态
        self.output_queue = Queue()
        self._recv_thread = None
        self._stop = False

    def connect(self, timeout=15):
        """建立交互式连接"""
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(hostname=self.host, port=self.port,
                           username=self.username, password=self.password,
                           timeout=timeout, banner_timeout=timeout, auth_timeout=timeout,
                           look_for_keys=False, allow_agent=False)

        # 打开交互式shell
        self.chan = self.client.invoke_shell(term='xterm', width=120, height=40)
        self.chan.settimeout(0.1)

        # 等待初始输出，获取提示符
        time.sleep(0.5)
        initial = self._recv_all()
        self.output_queue.put(initial)

        # 尝试提取提示符（取最后一行）
        lines = initial.strip().split('\n')
        if lines:
            self.prompt = lines[-1].strip()

        self.connected = True

        # 启动接收线程
        self._stop = False
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()
        return True

    def _recv_all(self):
        """接收所有可用数据"""
        data = ''
        for _ in range(50):
            try:
                chunk = self.chan.recv(4096).decode('utf-8', errors='replace')
                if not chunk:
                    break
                data += chunk
            except socket.timeout:
                break
            except Exception:
                break
        return data

    def _recv_loop(self):
        """后台接收线程"""
        while not self._stop:
            try:
                chunk = self.chan.recv(4096).decode('utf-8', errors='replace')
                if chunk:
                    self.output_queue.put(chunk)
            except socket.timeout:
                time.sleep(0.05)
            except Exception:
                if not self._stop:
                    self.output_queue.put('\r\n[连接已断开]\r\n')
                break

    def send(self, cmd):
        """发送命令"""
        if self.chan and self.connected:
            self.chan.send(cmd + '\n')
            return True
        return False

    def get_output(self, timeout=0.5):
        """获取输出"""
        data = ''
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                chunk = self.output_queue.get(timeout=0.1)
                data += chunk
            except Empty:
                break
        return data

    def _drain_output(self, max_wait=0.5):
        """清空待处理输出"""
        drained = ''
        deadline = time.time() + max_wait
        while time.time() < deadline:
            chunk = self.get_output(0.1)
            if not chunk:
                break
            drained += chunk
        return drained

    def _recv_until(self, patterns, timeout=15):
        """
        收集输出直到匹配到指定模式之一。
        patterns: [(pattern_regex, label), ...] 按顺序匹配，返回 (output, matched_label)
        超时返回 (output, None)
        """
        data = ''
        deadline = time.time() + timeout
        while time.time() < deadline:
            chunk = self.get_output(0.3)
            data += chunk
            for pattern, label in patterns:
                if re.search(pattern, data):
                    return data, label
            time.sleep(0.1)
        return data, None

    def exec_command(self, command, timeout=30):
        """执行单条命令并返回结果（普通用户）"""
        if not self.connected:
            return {'exitCode': -1, 'output': '未连接', 'duration': 0}

        start = time.time()
        # 清空待处理输出
        self._drain_output(0.1)
        # 发送命令
        self.chan.send(command + '\n')

        # 等待并收集输出
        output = ''
        deadline = time.time() + timeout

        while time.time() < deadline:
            chunk = self.get_output(0.3)
            output += chunk
            # 检测命令回显结束（出现提示符）
            lines = output.split('\n')
            if len(lines) >= 2:
                last_lines = '\n'.join(lines[-3:])
                if re.search(r'[\$#>%]\s*$', last_lines) and len(output) > len(command) + 2:
                    break
            time.sleep(0.1)

        duration = time.time() - start

        # 清理输出（去掉命令回显本身）
        cleaned = self._clean_output(output, command)

        return {
            'exitCode': 0,
            'output': cleaned,
            'rawOutput': output,
            'duration': duration,
        }

    @staticmethod
    def _strip_ansi(text):
        """去除所有 ANSI 转义序列（CSI / OSC / 其他控制序列），与 screenshot.clean_ansi 保持一致"""
        # CSI 序列: ESC [ 参数(数字;?等) 终止字母
        text = re.sub(r'\x1b\[[0-9;?]*[a-zA-Z]', '', text)
        # OSC 序列: ESC ] ... BEL(\x07) 或 ST(\x1b\\)
        text = re.sub(r'\x1b\].*?(\x07|\x1b\\)', '', text)
        # 其他 escape 序列 (如字符集选择 ESC ( B)
        text = re.sub(r'\x1b[^\[\]]', '', text)
        return text.replace('\r', '')

    def _clean_output(self, output, command):
        """清理输出：跳过命令回显和提示符行。使用完整 ANSI 清理"""
        lines = output.split('\n')
        result = []
        passed_echo = False
        for line in lines:
            clean = self._strip_ansi(line)
            # 标记命令回显已过去
            if not passed_echo and command.strip() in clean:
                passed_echo = True
                continue
            # 已过回显后，跳过纯提示符行
            if passed_echo:
                stripped = clean.strip()
                if re.match(r'^[\$#>%]\s*$', stripped):
                    continue
                # 跳过标准格式的提示符行（如 user@host:~$ / [root@host ~]#）
                if re.match(r'^[a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+:.*[\$#>%]\s*$', stripped):
                    continue
                if re.match(r'^\[?root@?.*[\]#]\s*$', stripped):
                    continue
            result.append(clean)
        return '\n'.join(result).strip()

    # ==================== Root 提权方法 ====================

    def su_switch(self, root_password, timeout=15):
        """
        在已有的交互式Shell中通过 su - root 切换到root。
        发送 "su - root" 后输入密码，验证提示符变化（$ -> #）。
        
        返回: {'success': bool, 'output': str, 'is_root': bool, 'reason': str}
        """
        if not self.connected:
            return {'success': False, 'output': '未连接', 'is_root': False, 'reason': '未连接'}

        # 清空待处理输出
        self._drain_output(0.1)

        # 步骤1: 发送 "su - root" 发起提权（- 参数加载完整环境变量）
        self.chan.send('su - root\n')
        time.sleep(0.3)

        # 步骤2: 等待密码提示（支持中英文）
        data, matched = self._recv_until([
            (r'[Pp]assword.*:', 'password_prompt'),
            (r'密码.*:', 'password_prompt_cn'),
            (r'incorrect password', 'bad_password'),
            (r'su: Authentication failure', 'auth_failure'),
        ], timeout=timeout)

        if matched == 'bad_password' or matched == 'auth_failure':
            return {
                'success': False,
                'output': self._clean_output(data, 'su - root'),
                'is_root': False,
                'reason': '认证失败：密码错误'
            }

        if matched != 'password_prompt' and matched != 'password_prompt_cn':
            return {
                'success': False,
                'output': self._clean_output(data, 'su - root'),
                'is_root': False,
                'reason': '未检测到密码提示，可能已配置免密su或su不可用'
            }

        # 步骤3: 发送密码
        self.chan.send(root_password + '\n')
        time.sleep(0.5)

        # 步骤4: 等待结果，检查是否提权成功
        data2, _ = self._recv_until([
            (r'[#$>%]\s*$', 'prompt'),
            (r'incorrect password', 'bad_password'),
            (r'su: Authentication failure', 'auth_failure'),
        ], timeout=timeout)

        combined_output = data + data2

        # 检查最后一行的提示符：root提示符通常以 # 结尾
        last_lines = combined_output.strip().split('\n')
        last_prompt = ''
        for line in reversed(last_lines):
            clean = re.sub(r'\x1b\[[0-9;]*[mKJHf]', '', line).replace('\r', '').strip()
            if clean and re.search(r'[\$#>%]', clean):
                last_prompt = clean
                break

        is_root = False
        if last_prompt and last_prompt.endswith('#'):
            self.is_root = True
            self.root_verified = True
            is_root = True
        else:
            # 额外验证：发送 whoami 确认
            self.chan.send('whoami\n')
            time.sleep(0.3)
            whoami_data = self._drain_output(0.5)
            if 'root' in whoami_data:
                self.is_root = True
                self.root_verified = True
                is_root = True

        if is_root:
            self.prompt = last_prompt if last_prompt else '[root@host ~]#'

        return {
            'success': is_root,
            'output': self._clean_output(combined_output, 'su - root'),
            'is_root': is_root,
            'reason': '提权成功' if is_root else '未检测到root提示符',
        }

    def execute_as_root(self, command, root_password, timeout=30):
        """
        以root身份执行命令。
        如果尚未提权，先通过 su 切换到root再执行命令。
        如果已提权，直接执行命令（此时已是root身份，无需额外提权）。

        返回: 标准命令结果 dict
        """
        if not self.connected:
            return {'exitCode': -1, 'output': '未连接', 'duration': 0}

        start = time.time()

        # 如果已在本会话中提权成功，直接执行命令
        if self.is_root and self.root_verified:
            result = self.exec_command(command, timeout=timeout)
            result['duration'] = time.time() - start
            return result

        # 尚未提权：先 su 切换再执行
        switch_result = self.su_switch(root_password, timeout=15)
        if not switch_result['success']:
            return {
                'exitCode': -1,
                'output': f"[su root 提权失败] {switch_result.get('reason', '未知错误')}\n{switch_result.get('output', '')}",
                'duration': time.time() - start,
            }

        # 提权成功后，已在root Shell中，直接执行命令
        result = self.exec_command(command, timeout=timeout)
        result['duration'] = time.time() - start
        return result

    def close(self):
        """关闭连接"""
        self._stop = True
        if self.chan:
            self.chan.close()
        if self.client:
            self.client.close()
        self.connected = False

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()


def quick_exec(host, port, username, password, command, timeout=30):
    """快速执行单条命令（非交互式）"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(hostname=host, port=port, username=username, password=password,
                       timeout=15, banner_timeout=15, auth_timeout=15,
                       look_for_keys=False, allow_agent=False)
        start = time.time()
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        output = stdout.read().decode('utf-8', errors='replace')
        err = stderr.read().decode('utf-8', errors='replace')
        if err and not output:
            output = err
        duration = time.time() - start
        return {'exitCode': exit_code, 'output': output, 'duration': duration}
    finally:
        client.close()


def check_regex(output, pattern):
    """正则匹配检查"""
    if not pattern or not output:
        return None
    try:
        return bool(re.search(pattern, output, re.MULTILINE))
    except re.error:
        return None