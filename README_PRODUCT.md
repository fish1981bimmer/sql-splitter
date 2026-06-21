# SQL Splitter

> SQL Server → 达梦数据库 一键迁移工具  
> 拆分SQL文件 + 自动语法转换 + 质量报告 + 兼容性评分

## 30秒体验

```bash
pip install sql-splitter

# 拆分 + 转换一条龙
sql-splitter input.sql output_dir --dialect sqlserver --convert-to dm
```

## 它解决什么问题？

信创替代场景下，大量SQL Server数据库需要迁移到达梦(DM)。传统做法是手工逐行改SQL——存储过程、函数、视图、触发器，每个都要改语法、换类型、调变量格式。一个项目几万行SQL，手改要1-2周，还容易出错。

SQL Splitter 做的就是这件事的自动化：

| 手工 | SQL Splitter |
|------|-------------|
| 1万行SQL手动改：1-2周 | 10秒 |
| 改错一处→生产事故 | 自动转换+质量报告 |
| 每个新版SQL都要重新改 | 批量处理+断点续传 |

## 核心功能

- **SQL文件拆分** — 将单个SQL文件拆分为独立的对象文件（存储过程、函数、视图、触发器、表、索引、约束）
- **达梦自动转换** — 40+数据类型映射、30+函数映射、变量/异常/事务/临时表语法转换
- **依赖分析** — 自动分析对象间依赖，生成按顺序执行的合并脚本
- **质量报告** — 转换后生成兼容性评分(0-100) + 风险项标注 + HTML/Markdown/JSON报告
- **批量处理** — 多文件并行处理，支持目录递归
- **断点续传** — 大文件中断后可续传
- **多方言支持** — MySQL / PostgreSQL / Oracle / SQL Server / 达梦

## 安装

```bash
pip install sql-splitter
```

或从源码安装：

```bash
git clone https://github.com/fish1981bimmer/sql-splitter.git
cd sql-splitter
pip install -e .
```

## 使用方法

### 基本拆分

```bash
# 拆分SQL Server文件
sql-splitter input.sql output_dir --dialect sqlserver

# 拆分并转换到达梦语法
python3 scripts/split_sql_v22.py input.sql output_dir --dialect sqlserver --convert-to dm
```

### 批量转换（推荐）

```bash
# Step 1: 拆分
python3 scripts/split_sql_v21.py input.sql output_dir --dialect sqlserver

# Step 2: 批量转换
python3 scripts/batch_convert.py output_dir output_dir_dm schema_prefix
```

### 质量报告

```python
from dm_converter import DMConverter
from report_generator import ConversionReportGenerator

converter = DMConverter()
result = converter.convert(sql_content, 'procedure', schema_prefix='hrbi')

# 单对象报告
report = ConversionReportGenerator.generate_single(result, 'sp_test', 'procedure')
print(report.to_markdown())   # Markdown格式
print(f'兼容性评分: {report.score}/100')

# 批量报告
batch = ConversionReportGenerator.generate_batch(results, schema_prefix='hrbi')
batch.save_html('report.html')   # 漂亮暗色主题HTML
batch.save_json('report.json')   # 结构化JSON
```

### GUI界面

```bash
sql-splitter --gui
```

### License管理

```bash
sql-splitter license status          # 查看当前版本
sql-splitter license activate KEY    # 激活专业版/企业版
sql-splitter license deactivate      # 注销License
sql-splitter license machine-id      # 显示机器指纹
```

## 版本对比

| 功能 | 社区版(免费) | 专业版 ¥299/月 | 企业版 ¥2999/月起 |
|------|:---:|:---:|:---:|
| SQL文件拆分 | ✅ ≤20对象 | ✅ 不限 | ✅ 不限 |
| 达梦自动转换 | ✅ ≤20对象 | ✅ 不限 | ✅ 不限 |
| 多方言支持 | ✅ | ✅ | ✅ |
| 依赖分析+合并脚本 | ✅ | ✅ | ✅ |
| 文件大小限制 | 1MB | 不限 | 不限 |
| 批量处理 | ❌ | ✅ | ✅ |
| 断点续传 | ❌ | ✅ | ✅ |
| 结果预览/DIFF | ❌ | ✅ | ✅ |
| 配置管理 | ❌ | ✅ | ✅ |
| 质量报告+兼容性评分 | ❌ | ✅ | ✅ |
| GUI界面 | ❌ | ✅ | ✅ |
| 自定义转换规则 | ❌ | ❌ | ✅ |
| API调用 | ❌ | 1000次/月 | 不限 |
| Docker私有部署 | ❌ | ❌ | ✅ |
| 数据脱敏 | ❌ | ❌ | ✅ |
| 技术支持 | GitHub Issue | 工单48h | 专属群+SLA |

**升级**: 访问 https://sqlsplitter.com 了解详情

## 转换规则速览

| 类别 | SQL Server | 达梦 |
|------|-----------|------|
| 声明 | CREATE PROCEDURE ... AS | CREATE OR REPLACE PROCEDURE ... AS |
| 数据类型 | INT/BIT/DATETIME/NVARCHAR | INTEGER/BOOLEAN/TIMESTAMP/VARCHAR(n CHAR) |
| 函数 | GETDATE()/ISNULL()/LEN() | CURRENT_TIMESTAMP/NVL()/LENGTH() |
| 变量 | @var / DECLARE @var | var / DECLARE var |
| 异常 | BEGIN TRY...END TRY | BEGIN...EXCEPTION WHEN OTHERS THEN...END |
| 事务 | COMMIT TRANSACTION | COMMIT |
| 清表 | TRUNCATE TABLE xxx | DELETE FROM xxx ⚠️ |
| 终止符 | GO | / |

## 已验证

- **53个单元测试** 全部通过
- **462个真实SQL对象** 端到端验证（HRBI_Stage.sql, 7万行）
- 涵盖：存储过程/函数/视图/触发器/表/索引/约束

## 开源协议

MIT-0 — 自由使用、修改、分发，无需署名

社区版功能永久免费开源。专业版和企业版功能需License授权。
