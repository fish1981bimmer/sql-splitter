# v3.3.0 修复记录

## 1. PROCEDURE双重引号bug

**症状**: `CREATE OR REPLACE PROCEDURE ""sp_test"" (p1 INT)" AS` — 名字被包了两层引号

**根因**: `_convert_procedure`中三个正则顺序执行:
1. `_format_bracket_params` 匹配 `PROC sp_test(...) AS` → 替换为 `PROCEDURE "sp_test" (...) AS`
2. `_format_no_bracket_params` 无匹配（已处理）
3. `_fmt_no_param_proc` 的正则 `PROC\s+(.+?)\s+AS` 又匹配了已替换的结果！把 `"sp_test"(...)` 当成name再包引号

**修复**: 合并三个正则+回调为一个统一正则 `_PROC_PATTERN` + 分支回调 `_format_proc`，确保每个存储过程声明只被匹配一次

**教训**: 多个re.sub顺序执行处理同类模式时，前面的替换结果会被后面的正则再次匹配。**绝不可以用多个re.sub顺序处理同一个token的不同形式**，必须用单一正则+分支回调，或者用标记跳过已处理的部分。

## 2. IDENTITY自增列位置修正

**症状**: `IDENTITY("id", 1, 1)` 出现在 `)` 前面（表定义内部），而不是 `)` 后面

**根因**: 原正则 `\)(\s*$|\s*;|...`) 匹配到 `VARCHAR(100 CHAR)\n)` 中的换行行尾，把IDENTITY插在了列定义和表结束`)`之间

**修复**: 改为匹配独占一行的 `)` (`^(\s*)\)(\s*$)`)，并fallback匹配行尾的 `)` (`\)(\s*(?:;|\n|$))`)。同时先用 `re.search` 定位再字符串拼接，避免re.sub的替换逻辑问题

**教训**: SQL中 `)` 出现在很多上下文(列类型VARCHAR(100)、函数调用、表定义结束)，匹配表结束的 `)` 必须用上下文锚定(独占一行/CREATE TABLE后/紧跟ON/GO等)

## 3. #临时表正则修复

**症状**: 临时表独立建表语句中列定义不完整，`NVARCHAR(100)` 之后的列丢失

**根因**: 正则 `(\([^]]*(?:\([^]]*\)[^]]*)*\))` 中 `[^]]*` 遇到 `NVARCHAR(100)` 的 `)` 就停止匹配，把类型参数中的 `)` 当成表定义的结束

**修复**: 改用贪婪 `(.+)` + `re.DOTALL` 匹配到最后一个 `)`: `r'CREATE\s+TABLE\s+(#{1,2})(\w+)\s*\((.+)\)'`

**额外修复**: `##` 全局临时表被错误替换——原来 `re.sub(r'#(\w+)', ...)` 只替换了第二个 `#`，把 `##GlobalTemp` 变成了 `#tmp_GlobalTemp`。修复：先替换 `##`(双#) → `gtmp_`，再替换 `#`(单#) → `tmp_`

## 4. token_map碰撞修复

**症状**: 视图中字符串 `'N/A'` 变成了标识符 `"v_users"`

**根因**: 
- Step1 tokenize: `'N/A'` → `__TOKEN_0__`
- Step2 view转换: 添加 `"v_users"` 
- Step3 重新tokenize: `"v_users"` → `__TOKEN_0__` (counter从0重新开始!)
- merged_map.update() 覆盖: `__TOKEN_0__` = `"v_users"` (原来的 `'N/A'` 被覆盖)
- detokenize: `__TOKEN_0__` 还原为 `"v_users"`

**修复**: `_tokenize` 新增 `start_counter` 参数，Step3调用时传入 `max_key + 1`

**教训**: tokenize每轮的counter必须接续上一轮的最大值，否则key碰撞会静默覆盖数据。**任何生成占位符的系统重新运行时，必须从已存在key的最大值+1开始**。

## 5. _quote_name方括号处理bug

**症状**: `[dbo].[PROC_xxx]` → `"dbo]"."[PROC_xxx"` (方括号只有一边被去掉)

**根因**: `_quote_name` 先检查整体是否 `[...body...]` 格式，`[dbo].[PROC_xxx]` 以 `[` 开头 `]` 结尾所以匹配，去掉首尾后变成 `dbo].[PROC_xxx`，再split `.` → `dbo]` + `[PROC_xxx`

**修复**: 先检查 `.` 分隔，对每段单独去方括号/引号，再 `'"."'.join()`。只有无 `.` 的名字才检查整体方括号

**教训**: 当输入可能是 `schema.name` 格式时，**绝不能先对整体做方括号/引号去除外层处理**，必须先split再逐段处理。否则 `[a].[b]` 整体看起来以 `[` 开头 `]` 结尾，导致错误去首尾。
