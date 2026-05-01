#!/usr/bin/env python3
"""
测试 JSON 序列化替代 pickle 的安全性
"""

import json
import tempfile
import sys
from pathlib import Path

# 添加 scripts 目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from checkpoint import CheckpointManager, CheckpointData

def test_json_serialization():
    """测试 JSON 序列化功能"""
    print("测试 JSON 序列化替代 pickle...")

    # 创建临时目录
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = CheckpointManager(Path(tmpdir))

        # 创建测试检查点
        checkpoint = manager.create_checkpoint(
            input_file="/test/input.sql",
            output_dir="/test/output",
            dialect="oracle",
            total_objects=100
        )

        # 更新检查点
        checkpoint = manager.update_checkpoint(checkpoint, processed_file="proc_test.sql")
        checkpoint = manager.update_checkpoint(checkpoint, processed_file="func_test.sql")

        # 保存检查点
        assert manager.save_checkpoint(checkpoint), "保存检查点失败"
        print("✓ 检查点保存成功")

        # 验证文件格式为 JSON
        checkpoint_file = manager.get_checkpoint_file("/test/input.sql")
        with open(checkpoint_file, 'r', encoding='utf-8') as f:
            content = f.read()
            # 验证是 JSON 格式
            data = json.loads(content)
            assert data['input_file'] == "/test/input.sql"
            assert data['processed_objects'] == 2
            print("✓ 检查点文件格式正确（JSON）")

        # 加载检查点
        loaded_checkpoint = manager.load_checkpoint("/test/input.sql")
        assert loaded_checkpoint is not None, "加载检查点失败"
        assert loaded_checkpoint.input_file == "/test/input.sql"
        assert loaded_checkpoint.processed_objects == 2
        print("✓ 检查点加载成功")

        # 列出检查点
        checkpoints = manager.list_checkpoints()
        assert len(checkpoints) == 1
        assert checkpoints[0]['input_file'] == "/test/input.sql"
        print("✓ 检查点列表正确")

        # 获取恢复进度
        resume_info = manager.get_resume_progress("/test/input.sql")
        assert resume_info is not None
        assert resume_info['progress'] == 0.02
        assert resume_info['can_resume'] == True
        print("✓ 恢复进度正确")

        # 删除检查点
        assert manager.delete_checkpoint("/test/input.sql"), "删除检查点失败"
        print("✓ 检查点删除成功")

    print("\n✓ 所有 JSON 序列化测试通过！")

if __name__ == "__main__":
    test_json_serialization()
