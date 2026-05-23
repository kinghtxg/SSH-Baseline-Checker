"""
pytest 全局配置 - SSH-Baseline-Checker
"""
import os
import sys
import pytest

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 设置测试模式环境变量
os.environ['FLASK_ENV'] = 'testing'
os.environ['SECRET_KEY'] = 'test-secret-key-for-pytest'


@pytest.fixture(scope='session')
def project_root():
    """项目根目录"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope='session')
def test_data_dir(tmp_path_factory):
    """测试数据临时目录"""
    return tmp_path_factory.mktemp('test_data')