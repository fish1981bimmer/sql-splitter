#!/usr/bin/env python3
"""
SQL 拆分工具 - 转换质量报告生成器
分析 DMConverter 的转换结果，生成结构化质量报告 + 兼容性评分

用法:
  # 单对象报告
  from dm_converter import DMConverter
  from report_generator import ConversionReportGenerator
  
  converter = DMConverter()
  result = converter.convert(sql, 'procedure', schema_prefix='hrbi')
  report = ConversionReportGenerator.generate_single(result, 'sp_test', 'procedure')
  print(report.to_markdown())
  print(f'兼容性评分: {report.score}')
  
  # 批量报告
  results = [{'name': 'sp_test', 'type': 'procedure', 'result': result}, ...]
  batch_report = ConversionReportGenerator.generate_batch(results, schema_prefix='hrbi')
  print(batch_report.to_markdown())
  batch_report.save_json('report.json')
  batch_report.save_html('report.html')
"""

import json
import os
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from collections import Counter

# === 数据类 ===

# 转换风险等级
RISK_LOW = 'low'       # 安全转换，语义等价
RISK_MEDIUM = 'medium' # 语义有差异但可接受
RISK_HIGH = 'high'     # 需人工确认

# 风险等级权重 (用于评分)
RISK_WEIGHTS = {
    RISK_LOW: 0,       # 不扣分
    RISK_MEDIUM: 2,    # 每项扣2分
    RISK_HIGH: 10,     # 每项扣10分
}

# 修改类型 → 风险等级映射
CHANGE_RISK_MAP = {
    # 语法声明类 — 安全
    'procedure': RISK_LOW,
    'function': RISK_LOW,
    'view': RISK_LOW,
    'trigger': RISK_LOW,
    'table': RISK_LOW,
    'index': RISK_LOW,
    
    # 类型映射 — 安全
    'data_type': RISK_LOW,
    'global_var': RISK_LOW,
    'transaction': RISK_LOW,
    'string_concat': RISK_LOW,
    'label': RISK_LOW,
    'interval': RISK_LOW,
    
    # 函数映射 — 安全
    'function_map': RISK_LOW,
    
    # 语句类 — 中等风险
    'statement': RISK_LOW,     # SET NOCOUNT等删除是安全的
    'variable': RISK_LOW,
    'if_else': RISK_LOW,
    'while': RISK_LOW,
    'exec': RISK_MEDIUM,       # 动态SQL需确认
    'print': RISK_LOW,
    'top': RISK_LOW,
    'try_catch': RISK_LOW,
    
    # 高风险
    'temp_table': RISK_MEDIUM,  # 临时表需确认达梦GTT语法
    'merge': RISK_HIGH,         # MERGE兼容性需逐个验证
    'truncate': RISK_HIGH,      # TRUNCATE→DELETE语义不等价
}

# 高风险关键词检测
HIGH_RISK_KEYWORDS = [
    'TRUNCATE', 'MERGE', 'CURSOR', 'CLR', 'XML',
    'OPENROWSET', 'OPENDATASOURCE', 'LINKED SERVER',
    'xp_cmdshell', 'sp_OACreate', 'Assembly',
]

MEDIUM_RISK_KEYWORDS = [
    'EXEC(@', 'EXECUTE IMMEDIATE', 'sp_executesql',
    '临时表', 'GTT', 'IDENTITY', '#temp', '##global',
    '动态SQL', 'MERGE语句',
]

# 修改类型中文标签
TYPE_LABELS = {
    'procedure': '存储过程声明',
    'function': '函数声明',
    'view': '视图声明',
    'trigger': '触发器声明',
    'table': '表结构',
    'index': '索引',
    'data_type': '数据类型',
    'function_map': '函数映射',
    'global_var': '全局变量',
    'statement': '语句映射',
    'variable': '变量转换',
    'transaction': '事务语法',
    'try_catch': '异常处理',
    'top': 'TOP子句',
    'temp_table': '临时表',
    'exec': '动态SQL',
    'print': '输出函数',
    'merge': 'MERGE语句',
    'label': '标签语法',
    'interval': 'INTERVAL',
    'string_concat': '字符串连接',
    'if_else': 'IF-ELSE控制流',
    'while': 'WHILE循环',
    'truncate': 'TRUNCATE→DELETE',
}

# 评分颜色阈值
SCORE_COLORS = {
    (90, 100): '#22c55e',  # 绿
    (70, 89):  '#eab308',   # 黄
    (50, 69):  '#f97316',   # 橙
    (0, 49):   '#ef4444',   # 红
}


@dataclass
class SingleReport:
    """单个对象的转换报告"""
    name: str                      # 对象名
    obj_type: str                  # 对象类型 (procedure/function/view/...)
    changes: List[Dict]            # 转换明细
    change_count: int              # 转换数量
    risk_items: List[Dict]        # 风险项列表 [{level, type, old, new, desc, reason}]
    score: int = 100               # 兼容性评分 (0-100)
    risk_level: str = RISK_LOW     # 综合风险等级
    warning: str = ''              # 重要警告
    original_lines: int = 0       # 原始行数
    converted_lines: int = 0      # 转换后行数
    
    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'type': self.obj_type,
            'score': self.score,
            'risk_level': self.risk_level,
            'change_count': self.change_count,
            'changes': self.changes,
            'risk_items': self.risk_items,
            'warning': self.warning,
            'original_lines': self.original_lines,
            'converted_lines': self.converted_lines,
        }
    
    def to_markdown(self) -> str:
        """生成Markdown格式报告"""
        lines = []
        lines.append(f'### {self.name} ({self.obj_type})')
        lines.append('')
        
        # 评分
        lines.append(f'- **兼容性评分**: {self.score}/100')
        lines.append(f'- **风险等级**: {_risk_label(self.risk_level)}')
        lines.append(f'- **转换数量**: {self.change_count} 处')
        
        if self.original_lines > 0:
            lines.append(f'- **原始行数**: {self.original_lines}')
            lines.append(f'- **转换后行数**: {self.converted_lines}')
        
        if self.warning:
            lines.append(f'- **⚠️ 警告**: {self.warning}')
        
        lines.append('')
        
        # 转换明细
        if self.changes:
            lines.append('#### 转换明细')
            lines.append('')
            lines.append('| # | 类型 | 原始 | 转换后 | 说明 |')
            lines.append('|---|------|------|--------|------|')
            for i, ch in enumerate(self.changes, 1):
                type_label = TYPE_LABELS.get(ch.get('type', ''), ch.get('type', ''))
                old_text = _truncate(ch.get('old', ''), 40)
                new_text = _truncate(ch.get('new', ''), 40)
                desc = ch.get('desc', '')
                lines.append(f'| {i} | {type_label} | `{old_text}` | `{new_text}` | {desc} |')
            lines.append('')
        
        # 风险项
        if self.risk_items:
            lines.append('#### ⚠️ 风险项')
            lines.append('')
            for ri in self.risk_items:
                icon = {'low': '✅', 'medium': '⚠️', 'high': '🔴'}[ri['level']]
                lines.append(f'{icon} **{ri["reason"]}** — {ri["desc"]}')
            lines.append('')
        
        return '\n'.join(lines)


@dataclass
class BatchReport:
    """批量转换报告"""
    schema_prefix: str
    total_objects: int = 0
    total_changes: int = 0
    objects: List[SingleReport] = field(default_factory=list)
    type_stats: Dict[str, int] = field(default_factory=dict)   # {type: count}
    risk_stats: Dict[str, int] = field(default_factory=dict)   # {level: count}
    overall_score: int = 100
    generated_at: str = ''
    high_risk_summary: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            'schema_prefix': self.schema_prefix,
            'generated_at': self.generated_at,
            'overall_score': self.overall_score,
            'total_objects': self.total_objects,
            'total_changes': self.total_changes,
            'type_stats': self.type_stats,
            'risk_stats': self.risk_stats,
            'high_risk_summary': self.high_risk_summary,
            'objects': [o.to_dict() for o in self.objects],
        }
    
    def to_markdown(self) -> str:
        """生成批量Markdown报告"""
        lines = []
        lines.append(f'# SQL Server → 达梦 转换质量报告')
        lines.append('')
        lines.append(f'**Schema**: {self.schema_prefix}')
        lines.append(f'**生成时间**: {self.generated_at}')
        lines.append('')
        
        # 总览
        lines.append('## 总览')
        lines.append('')
        lines.append(f'| 指标 | 值 |')
        lines.append(f'|------|-----|')
        lines.append(f'| 总对象数 | {self.total_objects} |')
        lines.append(f'| 总转换数 | {self.total_changes} |')
        lines.append(f'| **综合兼容性评分** | **{self.overall_score}/100** |')
        
        # 风险统计
        low = self.risk_stats.get(RISK_LOW, 0)
        medium = self.risk_stats.get(RISK_MEDIUM, 0)
        high = self.risk_stats.get(RISK_HIGH, 0)
        lines.append(f'| ✅ 低风险对象 | {low} |')
        lines.append(f'| ⚠️ 中风险对象 | {medium} |')
        lines.append(f'| 🔴 高风险对象 | {high} |')
        lines.append('')
        
        # 类型统计
        if self.type_stats:
            lines.append('### 对象类型分布')
            lines.append('')
            lines.append('| 类型 | 数量 |')
            lines.append('|------|------|')
            for t, c in sorted(self.type_stats.items(), key=lambda x: -x[1]):
                lines.append(f'| {t} | {c} |')
            lines.append('')
        
        # 评分排名
        if self.objects:
            lines.append('### 对象兼容性评分排名')
            lines.append('')
            lines.append('| 对象名 | 类型 | 评分 | 风险 |')
            lines.append('|--------|------|------|------|')
            # 按评分升序（问题多的排前面）
            sorted_objs = sorted(self.objects, key=lambda o: o.score)
            for obj in sorted_objs:
                risk_icon = {'low': '✅', 'medium': '⚠️', 'high': '🔴'}[obj.risk_level]
                lines.append(f'| {obj.name} | {obj.obj_type} | {obj.score} | {risk_icon} |')
            lines.append('')
        
        # 高风险汇总
        if self.high_risk_summary:
            lines.append('### 🔴 高风险项汇总（需人工确认）')
            lines.append('')
            for i, item in enumerate(self.high_risk_summary, 1):
                lines.append(f'{i}. {item}')
            lines.append('')
        
        # 各对象详细报告
        lines.append('---')
        lines.append('')
        lines.append('## 对象详细报告')
        lines.append('')
        for obj in sorted(self.objects, key=lambda o: o.score):
            lines.append(obj.to_markdown())
        
        return '\n'.join(lines)
    
    def save_json(self, filepath: str):
        """保存为JSON"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
    
    def save_markdown(self, filepath: str):
        """保存为Markdown"""
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(self.to_markdown())
    
    def save_html(self, filepath: str):
        """保存为HTML"""
        html = _generate_html_report(self)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)


class ConversionReportGenerator:
    """转换质量报告生成器"""
    
    @staticmethod
    def generate_single(result, name: str, obj_type: str,
                        original_lines: int = 0, converted_lines: int = 0) -> SingleReport:
        """
        为单个转换结果生成报告
        
        Args:
            result: DMConverter.convert() 返回的 ConversionResult
            name: 对象名
            obj_type: 对象类型
            original_lines: 原始SQL行数
            converted_lines: 转换后SQL行数
        """
        changes = result.changes if hasattr(result, 'changes') else []
        change_count = len(changes)
        
        # 分析风险项
        risk_items = []
        score = 100
        warning = ''
        
        for ch in changes:
            ch_type = ch.get('type', '')
            desc = ch.get('desc', '')
            old_val = ch.get('old', '')
            new_val = ch.get('new', '')
            
            # 判断风险等级
            risk = _assess_change_risk(ch_type, desc, old_val, new_val)
            
            if risk == RISK_HIGH:
                score -= RISK_WEIGHTS[RISK_HIGH]
                risk_items.append({
                    'level': RISK_HIGH,
                    'type': ch_type,
                    'old': old_val,
                    'new': new_val,
                    'desc': desc,
                    'reason': _risk_reason(ch_type, desc, old_val),
                })
            elif risk == RISK_MEDIUM:
                score -= RISK_WEIGHTS[RISK_MEDIUM]
                risk_items.append({
                    'level': RISK_MEDIUM,
                    'type': ch_type,
                    'old': old_val,
                    'new': new_val,
                    'desc': desc,
                    'reason': _risk_reason(ch_type, desc, old_val),
                })
        
        # 检测未转换的高风险关键词
        original_sql = result.original if hasattr(result, 'original') else ''
        for kw in HIGH_RISK_KEYWORDS:
            if kw.lower() in original_sql.lower():
                risk_items.append({
                    'level': RISK_HIGH,
                    'type': 'unconverted',
                    'old': kw,
                    'new': '',
                    'desc': f'检测到未转换的高风险关键词: {kw}',
                    'reason': f'{kw} 在达梦中无等价语法，需人工处理',
                })
                score -= 5
        
        # 评分下限保护
        score = max(0, score)
        
        # 综合风险等级
        if any(ri['level'] == RISK_HIGH for ri in risk_items):
            risk_level = RISK_HIGH
        elif any(ri['level'] == RISK_MEDIUM for ri in risk_items):
            risk_level = RISK_MEDIUM
        else:
            risk_level = RISK_LOW
        
        # 关键警告
        for ri in risk_items:
            if ri['level'] == RISK_HIGH:
                if ri['type'] == 'truncate':
                    warning = 'TRUNCATE→DELETE: DELETE不重置IDENTITY/自增序列，且可回滚'
                elif ri['type'] == 'merge':
                    warning = 'MERGE语句在达梦中的兼容性需逐个验证'
                elif ri['type'] == 'unconverted':
                    warning = ri['desc']
                break
        
        return SingleReport(
            name=name,
            obj_type=obj_type,
            changes=changes,
            change_count=change_count,
            risk_items=risk_items,
            score=score,
            risk_level=risk_level,
            warning=warning,
            original_lines=original_lines,
            converted_lines=converted_lines,
        )
    
    @staticmethod
    def generate_batch(results: List[Dict], schema_prefix: str = '') -> BatchReport:
        """
        为批量转换结果生成报告
        
        Args:
            results: [{'name': str, 'type': str, 'result': ConversionResult, 
                       'original_lines': int, 'converted_lines': int}]
            schema_prefix: schema前缀
        """
        objects = []
        total_changes = 0
        type_stats = Counter()
        risk_stats = Counter()
        high_risk_summary = []
        
        for item in results:
            result = item['result']
            name = item['name']
            obj_type = item.get('type', 'generic')
            orig_lines = item.get('original_lines', 0)
            conv_lines = item.get('converted_lines', 0)
            
            report = ConversionReportGenerator.generate_single(
                result, name, obj_type, orig_lines, conv_lines
            )
            objects.append(report)
            
            total_changes += report.change_count
            type_stats[obj_type] += 1
            risk_stats[report.risk_level] += 1
            
            # 收集高风险项
            for ri in report.risk_items:
                if ri['level'] == RISK_HIGH:
                    high_risk_summary.append(
                        f'{name}({obj_type}): {ri["reason"]}'
                    )
        
        # 计算综合评分 = 所有对象评分的平均值
        if objects:
            overall_score = int(sum(o.score for o in objects) / len(objects))
        else:
            overall_score = 100
        
        return BatchReport(
            schema_prefix=schema_prefix,
            total_objects=len(objects),
            total_changes=total_changes,
            objects=objects,
            type_stats=dict(type_stats),
            risk_stats=dict(risk_stats),
            overall_score=overall_score,
            generated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            high_risk_summary=high_risk_summary,
        )
    
    @staticmethod
    def quick_score(result) -> int:
        """快速获取兼容性评分（不生成完整报告）"""
        changes = result.changes if hasattr(result, 'changes') else []
        score = 100
        original = result.original if hasattr(result, 'original') else ''
        
        for ch in changes:
            risk = _assess_change_risk(
                ch.get('type', ''), ch.get('desc', ''),
                ch.get('old', ''), ch.get('new', '')
            )
            score -= RISK_WEIGHTS.get(risk, 0)
        
        for kw in HIGH_RISK_KEYWORDS:
            if kw.lower() in original.lower():
                score -= 5
        
        return max(0, score)


# === 内部工具函数 ===

def _assess_change_risk(ch_type: str, desc: str, old_val: str, new_val: str) -> str:
    """评估单条change的风险等级"""
    # 特殊处理TRUNCATE
    if 'TRUNCATE' in (old_val + desc).upper():
        return RISK_HIGH
    
    # 特殊处理MERGE
    if ch_type == 'merge' or 'MERGE' in desc.upper():
        return RISK_HIGH
    
    # 特殊处理动态SQL
    if ch_type == 'exec':
        return RISK_MEDIUM
    
    # 特殊处理临时表
    if ch_type == 'temp_table':
        return RISK_MEDIUM
    
    # 通用映射
    return CHANGE_RISK_MAP.get(ch_type, RISK_LOW)


def _risk_reason(ch_type: str, desc: str, old_val: str) -> str:
    """生成风险说明"""
    reasons = {
        'truncate': 'TRUNCATE→DELETE语义不等价: DELETE不重置IDENTITY、可回滚、不释放空间',
        'merge': 'MERGE语句在达梦中的语法和语义需逐个验证',
        'exec': '动态SQL (EXEC/sp_executesql) 在达梦中用EXECUTE IMMEDIATE，需确认SQL字符串拼接逻辑',
        'temp_table': '达梦临时表需用CREATE GLOBAL TEMPORARY TABLE定义，迁移后需手动确认GTT语法',
    }
    if ch_type in reasons:
        return reasons[ch_type]
    
    # 关键词匹配
    val_upper = (old_val + desc).upper()
    if 'CURSOR' in val_upper:
        return '游标语法在达梦中差异较大，需人工确认'
    if 'XML' in val_upper:
        return 'XML相关函数在达梦中支持有限'
    if 'CLR' in val_upper:
        return 'CLR程序集在达梦中不支持'
    
    return f'需确认转换正确性: {desc}'


def _risk_label(level: str) -> str:
    """风险等级标签"""
    return {
        RISK_LOW: '✅ 低风险',
        RISK_MEDIUM: '⚠️ 中风险',
        RISK_HIGH: '🔴 高风险',
    }.get(level, '未知')


def _truncate(text: str, max_len: int) -> str:
    """截断文本"""
    text = text.replace('|', '\\|').replace('\n', ' ')
    if len(text) > max_len:
        return text[:max_len - 3] + '...'
    return text


def _score_color(score: int) -> str:
    """评分颜色"""
    for (lo, hi), color in SCORE_COLORS.items():
        if lo <= score <= hi:
            return color
    return '#ef4444'


def _generate_html_report(batch: BatchReport) -> str:
    """生成HTML格式报告"""
    score_color = _score_color(batch.overall_score)
    
    # 对象行
    obj_rows = ''
    for obj in sorted(batch.objects, key=lambda o: o.score):
        obj_color = _score_color(obj.score)
        risk_icon = {'low': '✅', 'medium': '⚠️', 'high': '🔴'}[obj.risk_level]
        warning_text = f'<br><span style="color:#ef4444">⚠️ {obj.warning}</span>' if obj.warning else ''
        obj_rows += f'''
        <tr>
            <td>{obj.name}</td>
            <td>{obj.obj_type}</td>
            <td style="color:{obj_color};font-weight:bold">{obj.score}</td>
            <td>{risk_icon}</td>
            <td>{obj.change_count}</td>
            <td>{warning_text[4:] if obj.warning else '-'}</td>
        </tr>'''
    
    # 高风险项
    high_risk_html = ''
    if batch.high_risk_summary:
        items = ''.join(f'<li>{item}</li>' for item in batch.high_risk_summary)
        high_risk_html = f'''
        <div class="card high-risk">
            <h3>🔴 高风险项（需人工确认）</h3>
            <ol>{items}</ol>
        </div>'''
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SQL Server→达梦 转换质量报告</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background:#0f172a; color:#e2e8f0; padding:24px; }}
.container {{ max-width:960px; margin:0 auto; }}
h1 {{ font-size:24px; margin-bottom:8px; }}
.subtitle {{ color:#94a3b8; margin-bottom:24px; }}
.card {{ background:#1e293b; border-radius:12px; padding:24px; margin-bottom:16px; border:1px solid #334155; }}
.card.high-risk {{ border-color:#ef4444; }}
.score {{ font-size:48px; font-weight:900; color:{score_color}; }}
.score-label {{ color:#94a3b8; font-size:14px; }}
.stats {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:16px; }}
.stat {{ text-align:center; }}
.stat-value {{ font-size:28px; font-weight:700; }}
.stat-label {{ font-size:12px; color:#94a3b8; }}
table {{ width:100%; border-collapse:collapse; margin-top:12px; }}
th {{ text-align:left; padding:8px 12px; background:#334155; font-size:13px; color:#94a3b8; border-bottom:1px solid #475569; }}
td {{ padding:8px 12px; border-bottom:1px solid #1e293b; font-size:14px; }}
tr:hover {{ background:#334155; }}
.badge {{ display:inline-block; padding:2px 8px; border-radius:4px; font-size:12px; font-weight:600; }}
.badge-low {{ background:#22c55e20; color:#22c55e; }}
.badge-medium {{ background:#eab30820; color:#eab308; }}
.badge-high {{ background:#ef444420; color:#ef4444; }}
</style>
</head>
<body>
<div class="container">
<h1>SQL Server → 达梦 转换质量报告</h1>
<p class="subtitle">Schema: {batch.schema_prefix} | 生成时间: {batch.generated_at}</p>

<div class="card">
  <div style="display:flex;align-items:center;gap:32px">
    <div>
      <div class="score">{batch.overall_score}</div>
      <div class="score-label">综合兼容性评分 / 100</div>
    </div>
    <div class="stats">
      <div class="stat"><div class="stat-value">{batch.total_objects}</div><div class="stat-label">总对象数</div></div>
      <div class="stat"><div class="stat-value">{batch.total_changes}</div><div class="stat-label">总转换数</div></div>
      <div class="stat"><div class="stat-value" style="color:#22c55e">{batch.risk_stats.get(RISK_LOW,0)}</div><div class="stat-label">✅ 低风险</div></div>
      <div class="stat"><div class="stat-value" style="color:#ef4444">{batch.risk_stats.get(RISK_HIGH,0)}</div><div class="stat-label">🔴 高风险</div></div>
    </div>
  </div>
</div>

{high_risk_html}

<div class="card">
  <h3>对象兼容性评分</h3>
  <table>
    <tr><th>对象名</th><th>类型</th><th>评分</th><th>风险</th><th>转换数</th><th>警告</th></tr>
    {obj_rows}
  </table>
</div>

</div>
</body>
</html>'''
    return html


# === CLI入口 ===

if __name__ == '__main__':
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    # 演示：转换一个示例SQL并生成报告
    from dm_converter import DMConverter
    
    sample_sql = '''
CREATE PROCEDURE [dbo].[sp_user_report]
    @start_date DATETIME,
    @dept NVARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @count INT;
    DECLARE @sql NVARCHAR(MAX);
    
    SELECT @count = COUNT(*) FROM users WHERE dept = @dept;
    
    SET @sql = N'SELECT * FROM ' + @dept + '.report';
    EXEC sp_executesql @sql;
    
    TRUNCATE TABLE tmp_report;
    
    MERGE INTO report AS t
    USING tmp_report AS s
    ON t.id = s.id
    WHEN MATCHED THEN UPDATE SET t.val = s.val;
END
'''
    
    converter = DMConverter()
    result = converter.convert(sample_sql, 'procedure', schema_prefix='hrbi')
    
    report = ConversionReportGenerator.generate_single(
        result, 'sp_user_report', 'procedure',
        original_lines=len(sample_sql.strip().split('\n')),
        converted_lines=len(result.converted.strip().split('\n')),
    )
    
    print(report.to_markdown())
    print(f'\n兼容性评分: {report.score}/100')
    print(f'风险等级: {report.risk_level}')
