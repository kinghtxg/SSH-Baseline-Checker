"""
SSH引擎单元测试 - 使用 pytest + unittest.mock
"""
import pytest
import time
import socket
import re
import paramiko
from unittest.mock import Mock, patch, MagicMock, call
from ssh_engine import (
    test_ssh as _test_ssh, InteractiveShell, quick_exec, check_regex
)


class TestTestSSH:
    """测试 test_ssh 函数"""
    
    @patch('ssh_engine.paramiko.SSHClient')
    def test_test_ssh_success(self, mock_client_class):
        """测试连接成功"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        success, message = _test_ssh('192.168.1.1', 22, 'user', 'pass')
        
        assert success is True
        assert message == '连接成功'
        mock_client.set_missing_host_key_policy.assert_called_once()
        mock_client.connect.assert_called_once_with(
            hostname='192.168.1.1', port=22, username='user', password='pass',
            timeout=10, banner_timeout=10, auth_timeout=10,
            look_for_keys=False, allow_agent=False
        )
        mock_client.close.assert_called_once()
    
    @patch('ssh_engine.paramiko.SSHClient')
    def test_test_ssh_auth_failure(self, mock_client_class):
        """测试认证失败"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.connect.side_effect = paramiko.AuthenticationException('Auth failed')
        
        success, message = _test_ssh('192.168.1.1', 22, 'user', 'wrong')
        
        assert success is False
        assert '认证失败' in message
    
    @patch('ssh_engine.paramiko.SSHClient')
    def test_test_ssh_timeout(self, mock_client_class):
        """测试连接超时"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.connect.side_effect = socket.timeout()
        
        success, message = _test_ssh('192.168.1.1', 22, 'user', 'pass')
        
        assert success is False
        assert '连接超时' in message
    
    @patch('ssh_engine.paramiko.SSHClient')
    def test_test_ssh_socket_error(self, mock_client_class):
        """测试网络错误"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.connect.side_effect = socket.error('Network unreachable')
        
        success, message = _test_ssh('192.168.1.1', 22, 'user', 'pass')
        
        assert success is False
        assert '网络错误' in message


class TestInteractiveShell:
    """测试 InteractiveShell 类"""
    
    def setup_method(self):
        """每个测试方法前的设置"""
        self.shell = InteractiveShell('192.168.1.1', 22, 'testuser', 'testpass')
        self.shell.client = Mock()
        self.shell.chan = Mock()
        self.shell.connected = True
        self.shell.output_queue = Mock()
        self.shell._stop = False
    
    @patch('ssh_engine.paramiko.SSHClient')
    def test_connect_success(self, mock_client_class):
        """测试连接成功"""
        shell = InteractiveShell('192.168.1.1', 22, 'user', 'pass')
        mock_client = Mock()
        mock_chan = Mock()
        mock_client_class.return_value = mock_client
        mock_client.invoke_shell.return_value = mock_chan
        
        with patch('threading.Thread') as mock_thread_class:
            result = shell.connect()
            
            assert result is True
            assert shell.connected is True
            assert shell.client == mock_client
            assert shell.chan == mock_chan
            mock_client.set_missing_host_key_policy.assert_called_once()
            mock_client.connect.assert_called_once()
            mock_client.invoke_shell.assert_called_once_with(term='xterm', width=120, height=40)
            mock_thread_class.assert_called_once()
    
    def test_send_success(self):
        """测试发送命令成功"""
        mock_chan = Mock()
        self.shell.chan = mock_chan
        
        result = self.shell.send('ls -la')
        
        assert result is True
        mock_chan.send.assert_called_once_with('ls -la\n')
    
    def test_send_not_connected(self):
        """测试未连接时发送命令"""
        self.shell.connected = False
        self.shell.chan = None
        
        result = self.shell.send('ls -la')
        
        assert result is False
    
    def test_get_output(self):
        """测试获取输出"""
        mock_queue = Mock()
        mock_queue.get.side_effect = ['output1', 'output2', Empty]
        self.shell.output_queue = mock_queue
        
        with patch('time.time', side_effect=[0, 0.05, 0.1, 0.15, 0.2]):
            result = self.shell.get_output(timeout=0.2)
        
        assert result == 'output1output2'
        assert mock_queue.get.call_count >= 2
    
    def test_clean_output(self):
        """测试清理输出"""
        output = "testuser@host:~$ ls -la\n-rw-r--r-- 1 user user 1234 Jan 1 00:00 file.txt\n$ "
        command = "ls -la"
        
        result = self.shell._clean_output(output, command)
        
        # 应该去掉命令回显和提示符行
        assert 'testuser@host:~$' not in result
        assert '$' not in result
        assert 'file.txt' in result
    
    def test_clean_output_with_ansi(self):
        """测试清理带ANSI转义序列的输出"""
        output = "\x1b[32mtestuser@host:~$\x1b[0m ls -la\n\x1b[33mfile.txt\x1b[0m\n\x1b[32m$ \x1b[0m"
        command = "ls -la"
        
        result = self.shell._clean_output(output, command)
        
        # ANSI序列应该被移除
        assert '\x1b[' not in result
        assert 'file.txt' in result
    
    @patch('ssh_engine.re.search')
    def test_check_regex_success(self, mock_search):
        """测试正则匹配成功"""
        mock_search.return_value = True
        
        result = check_regex('output text', r'text')
        
        assert result is True
        mock_search.assert_called_once_with(r'text', 'output text', re.MULTILINE)
    
    def test_check_regex_none_pattern(self):
        """测试空正则模式"""
        result = check_regex('output', None)
        
        assert result is None
    
    def test_check_regex_none_output(self):
        """测试空输出"""
        result = check_regex(None, r'pattern')
        
        assert result is None
    
    def test_check_regex_invalid_pattern(self):
        """测试无效正则表达式"""
        result = check_regex('output', r'[invalid')
        
        assert result is None
    
    def test_sudo_switch_success(self):
        """测试sudo提权成功"""
        # 模拟交互式流程
        mock_chan = Mock()
        self.shell.chan = mock_chan
        self.shell._drain_output = Mock(return_value='')
        self.shell._recv_until = Mock(side_effect=[
            ('[sudo] password for user:', 'password_prompt'),
            ('user@host:~# ', 'prompt')
        ])
        self.shell._clean_output = Mock(return_value='cleaned output')
        
        result = self.shell.sudo_switch('rootpass', timeout=10)
        
        assert result['success'] is True
        assert result['is_root'] is True
        assert self.shell.is_root is True
        assert self.shell.root_verified is True
        mock_chan.send.assert_has_calls([
            call('sudo -S\n'),
            call('rootpass\n')
        ])
    
    def test_sudo_switch_not_connected(self):
        """测试未连接时sudo提权"""
        self.shell.connected = False
        
        result = self.shell.sudo_switch('rootpass')
        
        assert result['success'] is False
        assert '未连接' in result['output']
    
    def test_sudo_switch_sudoers_denied(self):
        """测试用户不在sudoers文件中"""
        self.shell._drain_output = Mock(return_value='')
        self.shell._recv_until = Mock(return_value=('user is not in the sudoers file', 'sudoers_denied'))
        self.shell._clean_output = Mock(return_value='cleaned')
        
        result = self.shell.sudo_switch('rootpass')
        
        assert result['success'] is False
        assert '该用户不在sudoers文件中' in result.get('reason', '')
    
    def test_execute_as_root_already_root(self):
        """测试已提权状态下执行root命令"""
        self.shell.is_root = True
        self.shell.root_verified = True
        self.shell._exec_sudo_command = Mock(return_value={
            'exitCode': 0, 'output': 'root output', 'rawOutput': 'raw', 'duration': 0
        })
        
        result = self.shell.execute_as_root('whoami', 'rootpass')
        
        assert result['exitCode'] == 0
        self.shell._exec_sudo_command.assert_called_once_with(
            'whoami', 'rootpass', expect_prompt=False, timeout=30
        )
    
    def test_execute_as_root_switch_fail(self):
        """测试提权失败后执行命令"""
        self.shell.sudo_switch = Mock(return_value={
            'success': False, 'output': 'switch failed', 'reason': 'bad password'
        })
        
        result = self.shell.execute_as_root('whoami', 'wrongpass')
        
        assert result['exitCode'] == -1
        assert 'sudo提权失败' in result['output']
    
    def test_close(self):
        """测试关闭连接"""
        mock_chan = Mock()
        mock_client = Mock()
        self.shell.chan = mock_chan
        self.shell.client = mock_client
        self.shell._stop = False
        
        self.shell.close()
        
        assert self.shell._stop is True
        assert self.shell.connected is False
        mock_chan.close.assert_called_once()
        mock_client.close.assert_called_once()


class TestQuickExec:
    """测试 quick_exec 函数"""
    
    @patch('ssh_engine.paramiko.SSHClient')
    def test_quick_exec_success(self, mock_client_class):
        """测试快速执行成功"""
        mock_client = Mock()
        mock_stdin = Mock()
        mock_stdout = Mock()
        mock_stderr = Mock()
        mock_channel = Mock()
        
        mock_client_class.return_value = mock_client
        mock_client.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stdout.read.return_value = b'command output'
        mock_stderr.read.return_value = b''
        
        with patch('time.time', side_effect=[0, 1.5]):
            result = quick_exec('192.168.1.1', 22, 'user', 'pass', 'ls -la', timeout=30)
        
        assert result['exitCode'] == 0
        assert result['output'] == 'command output'
        assert result['duration'] == 1.5
        mock_client.connect.assert_called_once()
        mock_client.exec_command.assert_called_once_with('ls -la', timeout=30)
        mock_client.close.assert_called_once()
    
    @patch('ssh_engine.paramiko.SSHClient')
    def test_quick_exec_with_error(self, mock_client_class):
        """测试快速执行有错误输出"""
        mock_client = Mock()
        mock_stdin = Mock()
        mock_stdout = Mock()
        mock_stderr = Mock()
        mock_channel = Mock()
        
        mock_client_class.return_value = mock_client
        mock_client.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)
        mock_stdout.channel.recv_exit_status.return_value = 1
        mock_stdout.read.return_value = b''
        mock_stderr.read.return_value = b'command not found'
        
        result = quick_exec('192.168.1.1', 22, 'user', 'pass', 'invalid_cmd')
        
        assert result['exitCode'] == 1
        assert result['output'] == 'command not found'
    
    @patch('ssh_engine.paramiko.SSHClient')
    def test_quick_exec_connection_error(self, mock_client_class):
        """测试快速执行连接错误"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.connect.side_effect = Exception('Connection refused')
        
        # quick_exec 不捕获异常，连接错误会向上抛出
        with pytest.raises(Exception, match='Connection refused'):
            quick_exec('192.168.1.1', 22, 'user', 'pass', 'ls')
        
        # 连接错误时应该关闭客户端
        mock_client.close.assert_called_once()


# 导入 Empty 异常用于测试
from queue import Empty

# 测试 check_regex 函数
def test_check_regex():
    """测试正则检查函数"""
    # 匹配成功
    assert check_regex('Active: active (running)', r'Active: active') is True
    # 匹配失败
    assert check_regex('Active: inactive', r'Active: active') is False
    # 空模式/空输出返回 None
    assert check_regex('any output', None) is None
    assert check_regex('', r'pattern') is None
    # 无效正则
    assert check_regex('test', r'[invalid') is None