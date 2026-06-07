---
name: sql-splitter
description: 拆分 SQL 文件为独立文件（存储过程、函数、视图、触发器、表结构、索引、约束），自动分析依赖并生成合并脚本
---

# SQL 文件拆分工具 v2.4.5

将包含多个 SQL 对象的单一文件或目录拆分为独立的 .sql 文件，
并自动分析对象间依赖关系，生成按依赖排序的合并脚本。

## v2.4.5 新功能 — 方括号转双引号 + dbo前缀智能处理 + 精确拆分

- **方括号→双引号** - `[schema].[table]` → `"schema"."table"`
 - 普通标识符 `[Users]` → `"Users"`
 - SQL类型名 `[nvarchar]` → `nvarchar`（去掉方括号+类型映射，不会变成`"nvarchar"`）
 - 支持30+种SQL Server类型名识别
- **dbo前缀智能处理** - 根据三段式/两段式自动判断
 - 三段式 `[HRBI].[dbo].[Users]` → `"HRBI"."Users"`（有schema前缀时，删除dbo.）
 - 两段式 `[dbo].[Users]` → `hrbi_stage."Users"`（无schema前缀时，用源文件名替换dbo）
 - schema_prefix从源文件名自动提取（如`hrbi_stage.sql` → 前缀`hrbi_stage`）
 - 支持双引号包裹格式：`"dbo"."Users"` 和裸名格式：`dbo.Users` 均可正确匹配
- **精确拆分增强** - 无明确终止符时的兜底逻辑
 - 新增`_find_next_create`函数：当找不到`;`或`GO`终止符时，用下一个`CREATE`关键字作为对象边界上界
 - 跳过字符串和注释内的`CREATE`，只匹配真正的CREATE语句开头
 - 所有对象类型（table/view/procedure/function/trigger/index/constraint）均有兜底
- **VARCHAR CHAR语义后处理** - `VARCHAR(n)` → `VARCHAR(n CHAR)`
 - 修复detokenize中类型名映射绕过CHAR语义的问题

- **重写达梦数据库转换器** - 完全重写 dm_converter.py
  - token化保护: 字符串/注释替换为占位符后再做正则替换，避免误改字符串内容
  - 按对象类型独立转换: procedure/function/view/trigger/table/index/constraint
  - 40+种数据类型映射, 30+种函数映射
  - 变量语法转换: @var -> var, DECLARE @var -> var, SET @var= -> var:=
  - TRY-CATCH -> EXCEPTION WHEN OTHERS THEN
  - 全局变量转换: @@ROWCOUNT -> SQL%ROWCOUNT
  - 触发器伪表: inserted/deleted -> NEW/OLD
  - 转换结果输出到子目录: output_split_dm/
- **拆分后转换集成** - split_sql_v21.py 新增 convert_to 参数
  - 拆分完成后自动调用转换器，按对象类型独立转换
  - 生成达梦版合并脚本 merge_all.sql
- **CLI参数** - split_sql_v22.py 新增 --convert-to dm
- **29个转换单元测试** - test_dm_converter.py 全部通过
- **修复已知bug**:
  - INSERT INTO 不再被误替换为 INTEGERO
  - token_map 合并避免占位符还原丢失
  - content = new_content 遗漏导致变量@替换无效
  - 嵌套括号 VARCHAR(100) 导致参数列表正则截断
  - 终止符 / 不再重复添加

### 达梦转换使用方法

```bash
# 拆分SQL Server文件并转换为达梦数据库语法
python3 ~/.openclaw/skills/sql-splitter/scripts/split_sql_v22.py input.sql output_dir --dialect sqlserver --convert-to dm

# 仅转换(不拆分)
python3 -c "from dm_converter import convert_sqlserver_to_dm; print(convert_sqlserver_to_dm('SELECT GETDATE()', 'generic'))"
```

### 转换规则

| 类别 | SQL Server | 达梦 |
|------|-----------|------|
| 声明 | CREATE PROCEDURE ... AS | CREATE OR REPLACE PROCEDURE ... IS |
| 数据类型 | INT/BIT/DATETIME/MONEY/NVARCHAR/VARCHAR/UNIQUEIDENTIFIER | INTEGER/BOOLEAN/TIMESTAMP/DECIMAL(19,4)/VARCHAR(n CHAR)/CHAR(36) |
| 函数 | GETDATE()/ISNULL()/LEN()/CONVERT() | CURRENT_TIMESTAMP/NVL()/LENGTH()/CAST() |
| 变量 | @var / DECLARE @var / SET @var= | var / var / var:= |
| 异常 | BEGIN TRY...END TRY BEGIN CATCH...END CATCH | BEGIN...EXCEPTION WHEN OTHERS THEN...END; |
| 事务 | COMMIT TRANSACTION / ROLLBACK TRANSACTION | COMMIT / ROLLBACK |
| 全局变量 | @@ROWCOUNT / @@ERROR | SQL%ROWCOUNT / SQL%ERROR_CODE |
| 触发器 | inserted/deleted | NEW/OLD |
| 终止符 | GO | / |

### 输出目录结构

```
input_split/ ← 原始拆分结果
├── proc_sp_test.sql
├── table_users.sql
├── view_v_users.sql
└── merge_all.sql

input_split_dm/ ← 达梦转换版本
├── proc_sp_test.sql
├── table_users.sql
├── view_v_users.sql
└── merge_all.sql
```

### 支持的对象类型转换

| 对象类型 | 转换策略 |
|---------|---------|
| 存储过程 | CREATE OR REPLACE + IS + 参数@去除 + 终止符/ |
| 函数 | CREATE OR REPLACE + RETURN + IS + 终止符/ |
| 视图 | CREATE OR REPLACE + SCHEMABINDING去除 |
| 触发器 | CREATE OR REPLACE + inserted/deleted->NEW/OLD + 终止符/ |
| 表 | IDENTITY保留 + 表选项去除 + 类型映射 |
| 索引 | CLUSTERED/NONCLUSTERED去除 + INCLUDE去除 |
| 约束 | WITH NOCHECK去除 |

### 转换器核心设计要点（开发调试血泪史）
- **token化保护**: 字符串/注释替换为占位符后再做正则替换，避免误改字符串内容
- **token_map合并**: Step2对象类型转换后重新tokenize时，必须合并旧token_map，否则`__TOKEN_0__`等占位符还原丢失
- **变量@前缀**: 在token还原后再做，且用`_tokenize_strings_only`只保护字符串(不保护注释，注释里@变量也要转)
- **`content = new_content` 不可省略**: re.sub后必须更新content变量，否则后续替换基于旧文本
- **嵌套括号**: `VARCHAR(100)`中的`)`会截断`[^)]*`，参数列表匹配需用`(\([^)]*(?:\([^)]*\)[^)]*)*\))`匹配嵌套
- **数据类型上下文**: 前缀需包含`DECLARE\s+`，否则`DECLARE @v DATETIME`中的DATETIME不会被转换
- **INSERT INTO误匹配**: `INSERT INT`被匹配为前缀`\n`+列名`INSERT`+类型`INT`，需在数据类型替换中排除SQL关键字作为列名
- **⚠️ patch工具缩进陷阱（严重，已反复触发）**: patch工具修改Python缩进时极易出错：(1) else块内代码被放到块外 (2) if子块和if本身同缩进 (3) 修复脚本的缩进也可能不对（17空格vs16空格的1位偏差导致整个if块变成else子块）。**正确修复流程：用`xxd`或`sed -n 'Np' file | xxd`确认原始缩进的精确空格/tab数，再写Python脚本逐行替换lines[N] = '正确缩进内容\n'。每次patch后必须用`python3 -m py_compile dm_converter.py`验证。仅靠lint不够——py_compile才能发现缩进导致的SyntaxError/IndentationError**
- **⚠️ Python缓存陷阱**: 修改.py后pytest可能运行旧的`__pycache__/*.pyc`。修改后必须`find . -name '*.pyc' -delete`或`PYTHONDONTWRITEBYTECODE=1 python3 -m pytest ...`。否则改了代码但测试结果不变，误导调试方向
- **⚠️ write_file不能写代码文件**: Hermes的write_file工具会给内容添加`NNN|`行号前缀，导致Python文件损坏。**代码文件只能用patch工具或terminal的python脚本修改**。详见 [v2.4.3修复记录](references/dm-converter-v243-fixes.md)

### 运行转换测试

```bash
cd ~/.openclaw/skills/sql-splitter/scripts
python3 -m pytest test_dm_converter.py -v
```

## 支持的 SQL 方言

- MySQL
- PostgreSQL
- Oracle
- SQL Server
- 达梦 (DM)
- 通用 (Generic)

## v2.2.1 功能

- **GUI 界面** - 提供图形化界面进行 SQL 文件拆分操作
- **断点续传** - 支持记录处理进度，中断后可以继续处理
- **批量并行处理** - 支持同时处理多个 SQL 文件，提升处理速度
- **结果预览和对比** - 可视化查看拆分结果，支持与原始文件对比
- **配置文件管理** - 保存和加载常用配置，支持导入导出
- **详细错误处理** - 结构化错误信息，包含错误类型、上下文和修复建议
- **Dry-run 预览模式** - 预览拆分结果而不实际创建文件
- **安全修复** - pickle反序列化漏洞修复，检查点改用JSON序列化

## 支持的 SQL 对象类型

| 类型 | 前缀 | 说明 |
|------|------|------|
| 存储过程 | `proc_` | CREATE PROCEDURE |
| 函数 | `func_` | CREATE FUNCTION |
| 视图 | `view_` | CREATE VIEW |
| 触发器 | `trig_` | CREATE TRIGGER |
| 表结构 | `table_` | CREATE TABLE |
| 包 | `pkg_` | CREATE PACKAGE |
| 索引 | `idx_` | CREATE INDEX |
| 唯一索引 | `uidx_` | CREATE UNIQUE INDEX |
| 约束 | `con_` | ALTER TABLE ADD CONSTRAINT |
| 序列 | `seq_` | CREATE SEQUENCE |
| 同义词 | `syn_` | CREATE SYNONYM (Oracle) |
| 事件 | `evt_` | CREATE EVENT (MySQL) |
| 物化视图 | `mv_` | CREATE MATERIALIZED VIEW (PostgreSQL) |
| 类型 | `type_` | CREATE TYPE |

## v2.0 核心改进

### 边界检测重写
- 使用 **BEGIN...END 深度匹配**确定存储过程/函数/触发器边界
- 支持 IF...THEN...END IF、CASE...END CASE、LOOP...END LOOP 嵌套
- 不再依赖"下一个 CREATE 位置"做上界，**正确处理过程体内的嵌套 CREATE 语句**
- Oracle/DM: 通过 `/` 终止符定位；SQL Server: 通过 `GO` 定位
- PostgreSQL: 支持 `$$...$$` 包裹语法
- 字符串和注释内的分号/关键字不会干扰边界检测

### 依赖分析改进
- 函数调用检测改为**限定上下文模式**（:= 赋值、WHERE/HAVING 子句等），大幅减少误报
- SQL 关键字过滤表扩展到 150+ 个，涵盖内置函数、控制流、聚合等
- 自引用自动排除
- 循环依赖不再报错，按类型优先级追加

### 合并脚本方言适配
- Oracle/DM: `@@filename` + `SET DEFINE OFF`
- SQL Server: `:r filename` + `GO`
- PostgreSQL: `\i filename` + `ON_ERROR_STOP`
- MySQL: `source filename`
- 通用: 注释方式

### 架构优化
- 提取 `common.py` 共享模块：SQLDialect 枚举、对象前缀、类型优先级、关键字表
- `dependency_analyzer.py` 不再重复定义枚举，直接引用 common
- 拆分后自动调用依赖分析，生成 `merge_all.sql`
- 新增 37 个单元测试

## 使用方法

### GUI 模式（推荐）
```bash
python3 ~/.openclaw/skills/sql-splitter/scripts/gui.py
```

### 单文件拆分
```bash
python3 ~/.openclaw/skills/sql-splitter/scripts/split_sql_v22.py <input.sql> [output_dir]
```

### 批量拆分（目录）
```bash
python3 ~/.openclaw/skills/sql-splitter/scripts/split_sql_v22.py --batch <目录路径> [输出目录]
```

### 批量拆分（多个文件）
```bash
python3 ~/.openclaw/skills/sql-splitter/scripts/split_sql_v22.py --batch "file1.sql,file2.sql,file3.sql" [输出目录]
```

### 指定方言
```bash
python3 ~/.openclaw/skills/sql-splitter/scripts/split_sql_v22.py --dialect oracle input.sql
```

支持的方言：`mysql`, `postgresql`, `oracle`, `sqlserver`, `dm`, `generic`

### 不生成合并脚本
```bash
python3 ~/.openclaw/skills/sql-splitter/scripts/split_sql_v22.py --no-merge input.sql
```

### 预览结果
```bash
python3 ~/.openclaw/skills/sql-splitter/scripts/split_sql_v22.py --preview input.sql output_dir
```

### 检查点管理
```bash
# 列出所有检查点
python3 ~/.openclaw/skills/sql-splitter/scripts/split_sql_v22.py --checkpoint --list

# 查看恢复进度
python3 ~/.openclaw/skills/sql-splitter/scripts/split_sql_v22.py --checkpoint --resume input.sql

# 清理旧检查点
python3 ~/.openclaw/skills/sql-splitter/scripts/split_sql_v22.py --checkpoint --clear --days 7

# 删除检查点
python3 ~/.openclaw/skills/sql-splitter/scripts/split_sql_v22.py --checkpoint --delete input.sql
```

### 配置管理
```bash
# 列出所有配置
python3 ~/.openclaw/skills/sql-splitter/scripts/split_sql_v22.py --config --list

# 保存配置
python3 ~/.openclaw/skills/sql-splitter/scripts/split_sql_v22.py --config --save --name oracle --dialect oracle

# 加载配置
python3 ~/.openclaw/skills/sql-splitter/scripts/split_sql_v22.py --config --load --name oracle

# 导出配置
python3 ~/.openclaw/skills/sql-splitter/scripts/split_sql_v22.py --config --export --name oracle --export-path oracle_config.json

# 导入配置
python3 ~/.openclaw/skills/sql-splitter/scripts/split_sql_v22.py --config --import --import-path oracle_config.json --name oracle
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `input.sql` | 要拆分的 SQL 文件路径（单文件模式必需） |
| `--batch` | 批量模式标志 |
| `--dialect` | 指定 SQL 方言 |
| `--no-merge` | 不生成依赖排序的合并脚本 |
| `-q`, `--quiet` | 静默模式 |
| `output_dir` | 输出目录（可选，默认：原文件名_split） |

### 运行测试
```bash
cd ~/.openclaw/skills/sql-splitter/scripts
# 拆分测试
python3 -m unittest test_sql_splitter -v
# 达梦转换测试
python3 -m pytest test_dm_converter.py -v
```

## 输出示例

假设输入文件 `myapp.sql` 包含：
- 表 `users`
- 视图 `v_users`（依赖 users）
- 存储过程 `sp_update`（依赖 users）

输出：
```
myapp_split/
├── table_users.sql
├── view_v_users.sql
├── proc_sp_update.sql
└── merge_all.sql          ← 按依赖排序的合并脚本
```

`merge_all.sql` 内容（以 Oracle 为例）：
```sql
-- [1/3] table: users
@@table_users.sql

-- [2/3] view: v_users  -- depends on: users
@@view_v_users.sql

-- [3/3] procedure: sp_update  -- depends on: users
@@proc_sp_update.sql
```

## 文件结构

```
sql-splitter/
├── SKILL.md ← 本文档
├── V21_USAGE_GUIDE.md ← v2.1 使用指南
├── SECURITY.md ← 安全文档
├── requirements.txt ← 依赖
├── references/
│   ├── dm-converter-design.md ← 达梦转换器设计要点
│   └── dm-converter-v243-fixes.md ← v2.4.3 修复记录
└── scripts/
    ├── common.py ← 共享模块（枚举、常量、工具函数）
    ├── split_sql.py ← v2.0 主拆分脚本
    ├── split_sql_v21.py ← v2.1 主拆分脚本（带错误处理+转换集成）
    ├── split_sql_v22.py ← v2.2 主拆分脚本（集成所有新功能）
    ├── dm_converter.py ← 达梦数据库转换器 v2.0
    ├── dependency_analyzer.py ← 依赖分析器
    ├── error_handler.py ← 错误处理模块
    ├── gui.py ← GUI 界面
    ├── checkpoint.py ← 断点续传模块
    ├── batch_processor.py ← 批量并行处理模块
    ├── result_previewer.py ← 结果预览和对比模块
    ├── config_manager.py ← 配置文件管理模块
    ├── test_sql_splitter.py ← 拆分单元测试（37个）
    ├── test_v21_features.py ← v2.1 功能测试
    └── test_dm_converter.py ← 达梦转换单元测试（29个）
```

## 达梦转换器已知问题（v2.4.3）

> v2.4.3 修复了 9 个核心 BUG（DATEADD参数重排、SELECT INTO、IF/WHILE控制流、PRINT等），40个测试全部通过。详见 [v2.4.3修复记录](references/dm-converter-v243-fixes.md)

**仍需手动调整的项目：**
- STRING_AGG→LISTAGG 缺少 WITHIN GROUP 子句
- STUFF→OVERLAY、REPLICATE→RPAD 语义不完全对等
- 临时表 #temp → GTT/普通表
- EXEC/EXECUTE 动态SQL → EXECUTE IMMEDIATE
- RAISERROR → RAISE_APPLICATION_ERROR
- TOP n → ROWNUM/FETCH FIRST
- MERGE/游标/WITH(NOLOCK)/IF EXISTS 等差异

**v2.4.4 已修复的映射：**
- VARCHAR(n) → VARCHAR(n CHAR)：达梦VARCHAR默认BYTE语义，必须加CHAR才等效SQL Server的字符语义
- UNIQUEIDENTIFIER → CHAR(36)：达梦用CHAR(36)而非VARCHAR(36)，UUID是定长

## v2.4.1 新功能 — 拆分自动加 OR REPLACE

- **视图和存储过程自动添加 OR REPLACE** — 拆分时对 procedure/function/view/trigger 四类对象，自动将 `CREATE` 转为 `CREATE OR REPLACE`
 - 达梦和 Oracle 环境下对象已存在时需要 `OR REPLACE`，否则会报错
 - 已有 `OR REPLACE` 的语句不会重复添加
 - 所有方言均生效（不仅限于 DM/Oracle）
 - 实现在 split_sql_v21.py 的 `obj_content` 提取后、写入文件前

## 注意事项

- 使用正则+深度匹配识别 SQL 对象边界，对极复杂嵌套语法可能有局限
- 默认 UTF-8 编码，遇到编码问题自动 replace
- 建议先备份原文件
- 批量模式会自动创建以原文件名命名的子目录
- 自动检测 SQL 方言，也可手动指定
- 同名文件自动追加序号（如 `proc_sp_init_2.sql`）

## 常见问题

### 拆分结果不正确（多个对象混在一个文件中）

**症状**：拆分后生成的文件包含多个 SQL 对象，而不是每个对象一个文件。

**原因**：原始 SQL 文件中的对象缺少分号结束符。sql-splitter 依赖分号来确定对象的结束位置。

**解决方案**：为每个 SQL 语句添加分号。例如：

```sql
-- 错误：缺少分号
Create table a(
  Id int,
  Name varchar(10)
)

Create table b(
  Id int,
  Name varchar(10)
)

-- 正确：添加分号
Create table a(
  Id int,
  Name varchar(10)
);

Create table b(
  Id int,
  Name varchar(10)
);
```

**快速修复方法**：
```bash
# 使用 sed 为每个 CREATE 语句后的空行添加分号
sed -i '' '/^Create /,/^)/s/)$/);/' input.sql
```

### 视图未被识别

**症状**：拆分后没有生成视图文件，或视图被识别为其他对象类型。

**原因**：视图语法不规范，缺少 `AS` 关键字。

**解决方案**：修正视图语法，添加 `AS` 关键字。例如：

```sql
-- 错误：缺少 AS
create view v_a
(
select * from dual
);

-- 正确：添加 AS
CREATE VIEW v_a AS
SELECT * FROM dual;
```

### 存储过程/函数未被正确拆分

**症状**：多个存储过程混在一个文件中，或产生重复文件。

**原因**：存储过程语法不规范，缺少 `AS`/`BEGIN` 关键字或分隔符。

**解决方案**：根据数据库类型修正语法：

**SQL Server**：
```sql
-- 错误：缺少 AS 和 GO
create proc p_a
(
select * from dual
);
create proc p_b
(
select * from dual
);

-- 正确：添加 AS 和 GO
CREATE PROCEDURE p_a
AS
BEGIN
    SELECT * FROM dual;
END
GO

CREATE PROCEDURE p_b
AS
BEGIN
    SELECT * FROM dual;
END
GO
```

**Oracle/达梦**：
```sql
-- 错误：缺少 IS/AS 和 /
CREATE PROCEDURE p_a
BEGIN
    SELECT * FROM dual;
END

-- 正确：添加 IS/AS 和 /
CREATE OR REPLACE PROCEDURE p_a IS
BEGIN
    SELECT * FROM dual;
END;
/
```

**MySQL**：
```sql
-- 错误：缺少 DELIMITER
CREATE PROCEDURE p_a()
BEGIN
    SELECT * FROM dual;
END

-- 正确：使用 DELIMITER
DELIMITER //
CREATE PROCEDURE p_a()
BEGIN
    SELECT * FROM dual;
END //
DELIMITER ;
```

### 产生重复文件

**症状**：拆分后生成多个内容相同或相似的文件（如 `proc_p_a.sql` 和 `proc_p_a_2.sql`）。

**原因**：对象边界检测失败，通常由以下原因导致：
- 对象之间缺少分隔符（分号、GO、/ 等）
- 对象语法不规范（缺少 AS、BEGIN 等）
- 嵌套对象语法错误

**解决方案**：
1. 检查并修正原始 SQL 文件的语法
2. 确保每个对象之间有正确的分隔符
3. 使用 `--dialect` 参数明确指定数据库类型
4. 对于复杂情况，考虑手动拆分或使用数据库工具导出

### 预检查清单

在运行 sql-splitter 之前，建议检查以下内容：

- [ ] 每个 SQL 语句都有分号结束符
- [ ] 视图包含 `AS` 关键字
- [ ] 存储过程/函数包含 `AS`/`BEGIN` 关键字
- [ ] SQL Server 对象之间有 `GO` 分隔符
- [ ] Oracle/达梦 对象末尾有 `/` 终止符
- [ ] MySQL 存储过程使用 `DELIMITER`
- [ ] 对象名称没有特殊字符或保留字冲突
- [ ] 文件编码为 UTF-8

## 文档维护规范

- 功能描述按版本倒序排列：最新版本(v2.4.0)在最前，旧版本(v2.2.1等)在后
- 避免重复章节：同一功能（如达梦转换）只在一个版本章节下详细描述，其他地方引用即可
- 标题中的版本号必须与 clawhub 发布版本一致
- 更新日志保留完整历史，但主体部分只展开最新版和次新版

## 更新日志

### v2.4.5 (2026-06-08)
- **方括号→双引号** - `[schema].[table]` → `"schema"."table"`，类型名`[nvarchar]` → `nvarchar`（去掉方括号并做类型映射）
- **dbo前缀智能处理** - 三段式`[HRBI].[dbo].[Users]` → `"HRBI"."Users"`(删dbo)；两段式`[dbo].[Users]` → `hrbi_stage."Users"`(用文件名替换)
- **精确拆分增强** - 无`;`/`GO`终止符时，用下一个`CREATE`关键字作为对象边界兜底
- **VARCHAR CHAR语义后处理** - 修复detokenize类型映射绕过CHAR语义的问题
- **schema_prefix自动传递** - 从源文件名自动提取前缀传给dm_converter
- **40个测试全部通过**

### v2.4.4 (2026-06-07)
- **数据类型映射调整** - 按达梦最佳实践修正
 - VARCHAR(n) → VARCHAR(n CHAR)：达梦VARCHAR默认BYTE语义，必须加CHAR才等效SQL Server的字符语义
 - UNIQUEIDENTIFIER → CHAR(36)：达梦用CHAR(36)而非VARCHAR(36)，UUID是定长
- **40个测试全部通过**
- **patch缩进修复血泪史**：详见转换器核心设计要点的 ⚠️ 警告

### v2.4.3 (2026-06-06)
- **达梦转换器BUG修复** - 9个失败测试全部修复，40/40通过
 - BIT→BOOLEAN, TINYINT→SMALLINT 类型映射修正
 - NVARCHAR(n) → VARCHAR(n CHAR) 达梦字符语义转换
 - SET NOCOUNT ON注释格式修正（去掉原文关键字）
 - DATEADD专用转换方法（参数重排：DATEADD(day,n,date) → date + INTERVAL 'n' DAY）
 - SELECT赋值区分有无FROM（有FROM→SELECT INTO，无FROM→:=）
 - IF...BEGIN...END → IF...THEN...END IF 控制流转换
 - WHILE...BEGIN...END → WHILE...LOOP...END LOOP 控制流转换
 - PRINT → DBMS_OUTPUT.PUT_LINE 转换（+号连接改||）
- **v2.4.3修复记录**：[v2.4.3修复记录](references/dm-converter-v243-fixes.md)
- **Python缩进调试技巧**：[patch工具导致的缩进bug排查](references/python-indentation-debugging.md)

### v2.5.0 (2026-05-31)
- **变量命名规范** - DECLARE局部变量自动加v_前缀, 参数保持原名, 符合达梦开发规范
- **多变量DECLARE** - `DECLARE @v1 INT, @v2 VARCHAR(100)` 正确拆分为多行独立声明
- **类型映射修正** - bit->BOOLEAN, tinyint->SMALLINT (达梦无TINYINT)
- **dbo前缀替换扩展** - 存储过程/函数中的dbo.也被替换为schema前缀
- **存储过程参数格式化** - 参数换行缩进, 加括号, DECIMAL(18,2)等括号内逗号不被误拆
- **类型映射修复** - [datetime] DEFAULT等DEFAULT后缀场景也能正确映射
- **SELECT INTO变量名** - 与DECLARE声明保持一致, 自动加v_前缀

### v2.4.1 (2026-05-30)
- **拆分自动加 OR REPLACE** - 对 procedure/function/view/trigger 四类对象，自动将 CREATE 转为 CREATE OR REPLACE
 - 已有 OR REPLACE 的语句不重复添加
 - 所有方言均生效

### v2.4.0 (2026-05-23)
- **重写达梦数据库转换器** - 完全重写 dm_converter.py
  - token化保护: 字符串/注释替换为占位符后再做正则替换
  - 按对象类型独立转换: procedure/function/view/trigger/table/index/constraint
  - 40+种数据类型映射, 30+种函数映射
  - 变量语法转换: @var -> var, DECLARE @var -> var, SET @var= -> var:=
  - TRY-CATCH -> EXCEPTION WHEN OTHERS THEN
  - 全局变量转换: @@ROWCOUNT -> SQL%ROWCOUNT
  - 触发器伪表: inserted/deleted -> NEW/OLD
  - 转换结果输出到子目录: output_split_dm/
- **拆分后转换集成** - split_sql_v21.py 新增 convert_to 参数
  - 拆分完成后自动调用转换器，按对象类型独立转换
  - 生成达梦版合并脚本 merge_all.sql
- **CLI参数** - split_sql_v22.py 新增 --convert-to dm
- **29个转换单元测试** - test_dm_converter.py 全部通过
- **修复已知bug**:
  - INSERT INTO 不再被误替换为 INTEGERO
  - token_map 合并避免占位符还原丢失
  - content = new_content 遗漏导致变量@替换无效
  - 嵌套括号 VARCHAR(100) 导致参数列表正则截断
  - 终止符 / 不再重复添加

### v2.2.1 (2026-05-01)
- **安全修复** - 修复 pickle 反序列化漏洞
  - 将检查点文件序列化从 pickle 替换为 JSON
  - 添加数据验证，防止恶意数据注入
  - 所有测试通过，功能正常
- **新增安全文档** - 添加 SECURITY.md
  - 详细说明安全措施和最佳实践
  - 记录安全更新历史
  - 提供安全问题报告渠道
- **新增依赖管理** - 添加 requirements.txt
  - 明确列出所有依赖
  - 当前版本仅使用 Python 标准库
  - 减少供应链攻击风险

### v2.2.0 (2026-04-27)
- **新增 GUI 界面** - 提供图形化界面进行 SQL 文件拆分操作
  - 支持文件浏览、参数配置、进度显示
  - 实时输出日志和错误信息
  - 配置自动保存和加载
- **新增断点续传功能** - 支持记录处理进度，中断后可以继续处理
  - 自动保存处理进度到检查点文件
  - 支持查看恢复进度和状态
  - 支持清理旧检查点
- **新增批量并行处理** - 支持同时处理多个 SQL 文件，提升处理速度
  - 可配置最大并发数
  - 支持目录批量处理
  - 支持进度回调
- **新增结果预览和对比** - 可视化查看拆分结果，支持与原始文件对比
  - 生成详细的文件统计信息
  - 支持表格化显示
  - 支持与原始文件内容对比
- **新增配置文件管理** - 保存和加载常用配置，支持导入导出
  - 支持多配置管理
  - 支持 JSON/YAML 格式导入导出
  - 配置验证功能

### v2.0.2 (2026-04-24)
- **修复重复文件问题**：添加去重逻辑，避免同一对象被多个正则表达式重复匹配
  - 去重标准：相同起始位置、对象类型、对象名称
  - 解决 SQL Server 存储过程产生重复文件的问题
  - 新增去重功能测试用例

### v2.0.1 (2026-04-24)
- 文档更新：新增常见问题章节
  - 视图未被识别的解决方案（缺少 AS 关键字）
  - 存储过程/函数未被正确拆分的解决方案（缺少 AS/BEGIN/分隔符）
  - 产生重复文件的原因和解决方案
  - 预检查清单（运行前检查项）

### v2.0.0 (2026-04-19)
- 重写对象边界检测：BEGIN/END/IF/CASE/LOOP 深度匹配
- 不再依赖"下一个 CREATE"作为上界，修复嵌套 CREATE 截断问题
- 提取 `common.py` 共享模块，消除枚举重复定义
- 依赖分析器：限定上下文检测、扩展关键字过滤、自引用排除
- 合并脚本按方言适配（Oracle/SQL Server/PostgreSQL/MySQL/DM）
- 拆分后自动生成 merge_all.sql
- 新增 37 个单元测试
- SQL Server 正则修复：方括号标识符匹配

### v1.1.0 (2026-04-13)
- 新增索引支持：CREATE INDEX, CREATE UNIQUE INDEX
- 新增约束支持：ALTER TABLE ADD CONSTRAINT
- 所有 6 种方言均支持索引/约束识别
- 支持 CLUSTERED/NONCLUSTERED (SQL Server)
- 支持 BITMAP 索引 (Oracle/达梦)

### v1.0.0
- 初始版本