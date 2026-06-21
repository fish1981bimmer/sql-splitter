#!/usr/bin/env python3
"""report_generator 单元测试"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dm_converter import DMConverter
from report_generator import (
    ConversionReportGenerator, SingleReport, BatchReport,
    RISK_LOW, RISK_MEDIUM, RISK_HIGH
)

def test_basic_report():
    """测试基础报告生成"""
    converter = DMConverter()
    sql = "CREATE PROCEDURE test @p1 INT AS BEGIN RETURN @p1 END"
    result = converter.convert(sql, 'procedure', schema_prefix='hrbi')
    
    report = ConversionReportGenerator.generate_single(result, 'test', 'procedure')
    
    assert report.name == 'test'
    assert report.obj_type == 'procedure'
    assert report.change_count > 0
    assert 0 <= report.score <= 100
    assert report.risk_level in (RISK_LOW, RISK_MEDIUM, RISK_HIGH)
    assert isinstance(report.changes, list)
    
    # Markdown输出
    md = report.to_markdown()
    assert 'test' in md
    assert '兼容性评分' in md
    
    print(f'  ✅ basic_report: score={report.score}, risk={report.risk_level}, changes={report.change_count}')


def test_high_risk_truncate():
    """测试TRUNCATE→DELETE高风险检测"""
    converter = DMConverter()
    sql = "CREATE PROCEDURE sp_clean AS BEGIN TRUNCATE TABLE tmp_data; END"
    result = converter.convert(sql, 'procedure', schema_prefix='hrbi')
    
    report = ConversionReportGenerator.generate_single(result, 'sp_clean', 'procedure')
    
    # 应该检测到高风险
    assert report.risk_level == RISK_HIGH
    assert report.score < 100
    assert any('TRUNCATE' in ri.get('reason', '') or 'TRUNCATE' in ri.get('desc', '') 
               for ri in report.risk_items if ri['level'] == RISK_HIGH)
    
    print(f'  ✅ high_risk_truncate: score={report.score}, risk_items={len(report.risk_items)}')


def test_high_risk_merge():
    """测试MERGE高风险检测"""
    converter = DMConverter()
    sql = "CREATE PROCEDURE sp_merge AS BEGIN MERGE INTO t USING s ON t.id=s.id WHEN MATCHED THEN UPDATE SET t.v=s.v; END"
    result = converter.convert(sql, 'procedure', schema_prefix='hrbi')
    
    report = ConversionReportGenerator.generate_single(result, 'sp_merge', 'procedure')
    
    has_merge_risk = any(
        'MERGE' in (ri.get('reason', '') + ri.get('desc', '')).upper()
        for ri in report.risk_items
    )
    assert has_merge_risk, "应检测到MERGE高风险"
    
    print(f'  ✅ high_risk_merge: score={report.score}, has_merge_risk={has_merge_risk}')


def test_low_risk_simple():
    """测试低风险简单转换"""
    converter = DMConverter()
    sql = "CREATE VIEW v_test AS SELECT id, name FROM users"
    result = converter.convert(sql, 'view', schema_prefix='hrbi')
    
    report = ConversionReportGenerator.generate_single(result, 'v_test', 'view')
    
    assert report.risk_level == RISK_LOW
    assert report.score >= 90
    
    print(f'  ✅ low_risk_simple: score={report.score}, risk={report.risk_level}')


def test_batch_report():
    """测试批量报告"""
    converter = DMConverter()
    
    results = []
    test_cases = [
        ("CREATE VIEW v1 AS SELECT 1", 'v1', 'view'),
        ("CREATE PROCEDURE sp1 @p INT AS BEGIN SET NOCOUNT ON; SELECT @p END", 'sp1', 'procedure'),
        ("CREATE PROCEDURE sp2 AS BEGIN TRUNCATE TABLE t; END", 'sp2', 'procedure'),
    ]
    
    for sql, name, obj_type in test_cases:
        result = converter.convert(sql, obj_type, schema_prefix='hrbi')
        results.append({
            'name': name,
            'type': obj_type,
            'result': result,
        })
    
    batch = ConversionReportGenerator.generate_batch(results, schema_prefix='hrbi')
    
    assert batch.total_objects == 3
    assert batch.total_changes > 0
    assert 0 <= batch.overall_score <= 100
    assert batch.type_stats.get('view', 0) + batch.type_stats.get('procedure', 0) > 0
    
    # Markdown
    md = batch.to_markdown()
    assert 'SQL Server → 达梦 转换质量报告' in md
    assert '综合兼容性评分' in md
    
    # JSON序列化
    d = batch.to_dict()
    assert d['total_objects'] == 3
    json_str = json.dumps(d, ensure_ascii=False)
    assert 'total_objects' in json_str
    
    print(f'  ✅ batch_report: objects={batch.total_objects}, changes={batch.total_changes}, score={batch.overall_score}')


def test_quick_score():
    """测试快速评分"""
    converter = DMConverter()
    sql = "CREATE VIEW v AS SELECT 1"
    result = converter.convert(sql, 'view', schema_prefix='hrbi')
    
    score = ConversionReportGenerator.quick_score(result)
    assert 0 <= score <= 100
    
    print(f'  ✅ quick_score: {score}')


def test_save_files(tmp_path=None):
    """测试文件保存"""
    converter = DMConverter()
    result = converter.convert("CREATE VIEW v AS SELECT 1", 'view', schema_prefix='test')
    
    batch = ConversionReportGenerator.generate_batch([
        {'name': 'v', 'type': 'view', 'result': result}
    ], schema_prefix='test')
    
    # 用/tmp
    import tempfile
    tmp = tempfile.mkdtemp()
    
    json_path = os.path.join(tmp, 'report.json')
    md_path = os.path.join(tmp, 'report.md')
    html_path = os.path.join(tmp, 'report.html')
    
    batch.save_json(json_path)
    batch.save_markdown(md_path)
    batch.save_html(html_path)
    
    # 验证文件存在且非空
    for p in [json_path, md_path, html_path]:
        assert os.path.exists(p), f"文件不存在: {p}"
        size = os.path.getsize(p)
        assert size > 0, f"文件为空: {p}"
    
    # 验证JSON可解析
    with open(json_path) as f:
        data = json.load(f)
    assert data['total_objects'] == 1
    
    # 验证HTML包含关键内容
    with open(html_path) as f:
        html = f.read()
    assert 'SQL Server' in html
    assert '达梦' in html
    
    import shutil
    shutil.rmtree(tmp)
    
    print(f'  ✅ save_files: json/md/html all saved and verified')


if __name__ == '__main__':
    print('\n=== report_generator 测试 ===\n')
    test_basic_report()
    test_high_risk_truncate()
    test_high_risk_merge()
    test_low_risk_simple()
    test_batch_report()
    test_quick_score()
    test_save_files()
    print('\n✅ 全部测试通过!')
