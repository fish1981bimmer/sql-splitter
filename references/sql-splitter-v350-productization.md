# sql-splitter v3.5.0 产品化开发记录

## 日期: 2026-06-21

## 本次完成的工作

### 1. report_generator.py — 转换质量报告生成器

**设计思路**: dm_converter.py的`ConversionResult.changes`列表已经记录了每项转换的`{type, line, old, new, desc}`。report_generator只消费这些数据，零侵入。

**风险分级体系**:
- LOW: 类型映射、语法声明、函数映射（安全转换，语义等价）
- MEDIUM: 动态SQL(EXEC/sp_executesql)、临时表(#temp→GTT)（需确认）
- HIGH: TRUNCATE→DELETE(语义不等价)、MERGE(兼容性需逐个验证)、未转换关键词(CLR/XML等)

**评分算法**:
- 基础分100，LOW扣0分，MEDIUM扣2分/项，HIGH扣10分/项
- 未转换高风险关键词扣5分/个
- 下限保护: min=0
- 批量报告的综合评分 = 所有对象评分的算术平均

**输出格式**:
- `to_markdown()` — Markdown（含表格，适合CSDN/文档）
- `save_html()` — 暗色主题HTML（适合交付客户）
- `save_json()` — 结构化JSON（适合API/CI集成）
- `quick_score()` — 快速评分，不生成完整报告

**验证**: 7个测试全通过(basic_report, high_risk_truncate, high_risk_merge, low_risk_simple, batch_report, quick_score, save_files)

### 2. license_checker.py — 版本控制与License管理

**架构决策**: 一套代码 + 功能开关。不走多仓库分叉。

**版本限制矩阵**:
- community: ≤20对象, ≤1MB, 无批量/报告/GUI/断点续传/配置管理
- pro: 无限对象+文件, 批量/报告/GUI/断点续传/配置管理, 1000次API/月
- enterprise: 全部解锁 + 自定义规则 + 无限API + Docker私有部署

**License存储**: `~/.sql-splitter/license.json`
- Key格式: XXXX-XXXX-XXXX-XXXX (16位)
- 当前版: E开头=Enterprise, P开头=Pro（TODO: 后续对接RSA服务端验签）
- 绑定: 机器指纹(CPU+MAC+node SHA256前16位)

**功能守卫**: `require_feature(feature, name)` — 在CLI/GUI入口处调用，未授权则打印升级提示并exit(1)
**对象限制**: `check_object_limit(count)` — 在split_sql_v21.py scan后调用，超限返回错误SplitResult
**文件限制**: `check_file_size(bytes)` — 同上

**验证**: 激活/注销/对象拦截(25对象被拦→专业版激活后通过) 全流程OK

### 3. gui.py重写

从7行空壳改为完整tkinter GUI:
- 文件选择 + 输出目录选择 + 方言选择
- 转换开关 + 报告开关
- 日志tab + 质量报告tab
- Step1拆分 → Step2达梦转换 → Step3质量报告
- License守卫: require_feature('gui')

### 4. split入口加License检查

- `split_sql_v21.py` 第753行后: `check_file_size()` + `check_object_limit()`
- `split_sql_v22.py` main(): 每个模式分支(gui/batch/preview/checkpoint/config)加`require_feature()`

### 5. pip打包

- `pyproject.toml`: sql-splitter v3.5.0
- `src/sql_splitter/__init__.py`: 版本声明
- `src/sql_splitter/cli.py`: CLI入口(包装split_sql_v22.main + license子命令)
- `README_PRODUCT.md`: 产品级README(功能对比表+安装+使用+版本对比)

## 关键坑

### License检查必须放在正确的位置
- 对象计数在scan阶段（第753行之后）才能拿到`len(found_objects)`
- 太早还没有计数，太晚已经开始写文件了
- 文件大小检查可以在scan前（只要读了文件就知道大小）

### gui.py的import问题
- split_sql_v22.py原先是`from gui import SQLSplitterGUI`
- 旧gui.py只有7行stub，import直接报NameError
- 新gui.py定义了`class SQLSplitterGUI`和`def run_gui()`
- 但v22的import方式和gui.py的导出函数名需要匹配

### py_compile验证是必须的
- 每次修改.py后先用`python3 -m py_compile`验证语法
- 再跑`python3 -m pytest`确认无回归
- LSP的pyright警告(type hint类)可以忽略，运行时不影响

## 未完成

- [ ] pip install sql-splitter 发布到PyPI
- [ ] 落地页HTML (sqlsplitter.com)
- [ ] License服务端RSA验签（当前仅本地Key前缀判断）
- [ ] 支付对接（支付宝当面付）
