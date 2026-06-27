# dm_converter v3.4.5 修复记录

## 日期: 2026-06-26

## 修复概览

312个HRBI存储过程批量转换，7条用户规则全部验证通过。

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 转换失败数 | 0 (但规则不完整) | 0 |
| VARCHAR CHAR语义 | 2057处 | 2057处 OK |
| SELECT INTO CTAS | 0 (不支持) | 174处 OK |
| DDL缺分号 | 447处 | 0 OK |

---

## 修复1: dbo两段式无prefix时保留不替换(BUG)

**问题**: `_replace_dbo_prefix()`在两段式`dbo.xxx`且无schema_prefix时保留`dbo.`不替换，用户要求去掉dbo变成`xxx`。

**修复位置**: `_replace_dbo_prefix()` 两段式分支

**逻辑**:
- 有schema_prefix: `dbo.xxx` -> `{prefix}.xxx`
- 无schema_prefix: `dbo.xxx` -> `xxx` (去掉dbo.前缀)

---

## 修复2: DATETIME2->TIMESTAMP2而非TIMESTAMP(BUG)

**问题**: TYPE_MAPPINGS的key构建正则alternation时无排序，`DATETIME`排在`DATETIME2`前面抢先匹配，`DATETIME2`被拆成`DATETIME`+`2`变成`TIMESTAMP2`。

**根因**: Python正则`|` alternation从左到右匹配，公共前缀的类型名短者先匹配。

**修复**: 全局`_TYPE_NAMES_PATTERN`、`_FULL_TYPE_NAMES_PATTERN`、`_post_convert_table_types`和`_post_convert_generic_types`中的`_bare_type_pattern`均用`sorted(keys, key=len, reverse=True)`按长度降序排列。

**受影响位置(4处)**:
1. `convert()`方法构建`type_name_pattern`
2. `_post_convert_table_types()`构建`_bare_type_pattern`
3. `_post_convert_generic_types()`构建`_bare_type_pattern`
4. 任何新增的TYPE_MAPPINGS consumer

---

## 修复3: 方括号替换在token还原后执行导致注释内容被误改(架构BUG)

**问题**: `_post_convert_table_types`/`_post_convert_generic_types`中的`\[([^\]]+)\]`在Step 6.7(token还原后)执行，注释已还原为原始文本，注释中含方括号会被误匹配截断。

**修复**: 把方括号替换从Step 6.7移到Step 4 `_convert_bracket_identifiers()`中执行。

**关键设计**: 此时注释和字符串已被tokenize保护(`__TOKEN_N__`占位符)，方括号只出现在真实SQL代码中。

**正则改进**: `[^\]\n]+`非贪婪模式，避免同行多标识符贪婪匹配跨行截断。

**保持不变的行为**:
- 动态SQL字符串内的方括号不修改(字符串被tokenize保护)
- 注释中的`[`不修改(注释被tokenize保护)

---

## 修复4: SELECT INTO #临时表->CTAS创建GTT(新规则)

**问题**: 达梦不支持`SELECT ... INTO #新表 FROM ...`建表语法。

**转换规则**:
```sql
-- SQL Server
SELECT * INTO #tmp_xxx FROM source_table WHERE ...

-- 达梦 (CTAS)
CREATE GLOBAL TEMPORARY TABLE "tmp_xxx" AS SELECT * FROM source_table WHERE ...;
```

**识别标识**:
- `INTO #xxx` -> 临时表(#前缀)
- `INTO tmp_xxx` -> 临时表(tmp_前缀)
- `INTO gtmp_xxx` -> 全局临时表(gtmp_前缀)

**限制**: 非临时表的SELECT INTO暂不自动转换——与达梦变量赋值语法`SELECT expr INTO var FROM ...`形式相同，无法程序化区分。

**验证**: 312个存储过程中174处SELECT INTO临时表成功转为CTAS。

---

## 修复5: 过程体内DDL语句结尾加分号(新规则)

**问题**: 达梦存储过程体内每条DDL必须以`;`结尾，SQL Server不要求。

**实现**: `_ensure_ddl_semicolons()`方法(Step 8.5)，用状态机扫描过程体。

**状态机逻辑**:
1. 单行DDL: `DROP TABLE xxx` -> `DROP TABLE xxx;`
2. 跨行建表: 用括号深度跟踪，在`)`行补`;`
3. CTAS跨行: 遇到下条语句开头时给上一行补`;`
4. ON PRIMARY文件组: 去掉后补`;`

**仅对PROCEDURE/FUNCTION/TRIGGER类型执行**。

**验证**: DDL块缺分号数从447降为0。

---

## 修复6: schema_prefix参数贯穿调用链

**问题**: `_convert_split_output()`签名有schema_prefix参数但调用处没传，dbo替换永远不生效。

**修复**: `split_sql_file()`签名增加schema_prefix参数，CLI新增`--schema-prefix`参数默认从输入文件名提取。

**教训**: 新增参数到函数签名时，必须grep所有调用点确保传参。

---

## 批量转换命令

```bash
python3 batch_convert.py <src_dir> <dm_dir> <schema_prefix>
```

HRBI三大库: Stage=54, DW=157, DM=101个, 全部0失败。

---

## 待修复边缘case

1. 少量`CREATE TABLE #xxx`形式的#未被替换(约4-5处)
2. 非临时表SELECT INTO需设计更精确判别逻辑
