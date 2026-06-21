# sql-splitter 产品化规划

> 日期: 2026-06-21

## 现状盘点

### 模块价值评估

| 模块 | 代码行 | 成熟度 | 商业价值(★) | 版本归属 |
|------|--------|--------|------------|---------|
| dm_converter.py | 2263 | 生产级(53测试) | ★★★★★ | 全版本核心 |
| split_sql_v21.py | 1117 | 生产级 | ★★★★ | 全版本核心 |
| split_sql_v22.py | 327 | 高(CLI入口) | ★★★ | 全版本入口 |
| dependency_analyzer.py | 279 | 中高 | ★★★ | 专业版+ |
| batch_processor.py | 295 | 中 | ★★★ | 专业版+ |
| error_handler.py | 200 | 中 | ★★ | 全版本基础 |
| checkpoint.py | 313 | 中 | ★★ | 专业版+ |
| config_manager.py | 353 | 中 | ★★ | 专业版+ |
| result_previewer.py | 303 | 中 | ★★ | 专业版+ |
| common.py | 282 | 高 | 基础设施 | 全版本 |
| gui.py | 7 | 空壳 | ★ | 专业版+(待开发) |
| batch_convert.py | 60 | 基础 | ★★ | 专业版+ |

### 模块依赖关系

```
common.py ← 核心共享（零外部依赖）
  ├─ error_handler.py（零外部依赖）
  ├─ dependency_analyzer.py ← common
  ├─ split_sql_v21.py ← common, error_handler（零外部项目依赖）
  │    └─ split_sql_v22.py ← v21, gui, checkpoint, batch, previewer, config
  ├─ dm_converter.py（零外部项目依赖）← 最值钱的核心
  │    └─ batch_convert.py ← dm_converter
  ├─ batch_processor.py ← v21, error_handler, checkpoint（专业版）
  ├─ checkpoint.py（专业版）
  ├─ config_manager.py（专业版）
  └─ result_previewer.py（专业版）
```

关键发现：dm_converter.py和split_sql_v21.py都是零项目依赖的独立模块，天然适合作为核心引擎，增值模块以插件方式拼装。

## 版本功能矩阵

| 功能 | 社区版(免费) | 专业版 ¥299/月 | 企业版 ¥2999/月起 |
|------|:---:|:---:|:---:|
| SQL文件拆分 | ✅ ≤1MB | ✅ 不限 | ✅ 不限 |
| 基础达梦转换 | ✅ ≤20对象 | ✅ 不限 | ✅ 不限 |
| 多方言支持 | ✅ | ✅ | ✅ |
| 依赖分析+合并脚本 | ✅ 基础排序 | ✅ 含循环检测 | ✅ 自定义策略 |
| 批量处理 | ❌ | ✅ 并行4线程 | ✅ 不限线程 |
| 断点续传 | ❌ | ✅ | ✅ |
| 结果预览/DIFF | ❌ | ✅ | ✅ |
| 配置管理 | ❌ | ✅ | ✅ |
| 转换质量报告 | ❌ | ✅ | ✅ |
| 兼容性评分 | ❌ | ✅ | ✅ |
| 自定义转换规则 | ❌ | ❌ 预设规则 | ✅ 自定义DSL |
| GUI界面 | ❌ | ✅ | ✅ |
| API调用 | ❌ | 1000次/月 | 不限 |
| Docker私有部署 | ❌ | ❌ | ✅ |
| 数据脱敏 | ❌ | ❌ | ✅ |
| 技术支持 | GitHub Issue | 工单48h | 专属群+SLA |
| 定制规则开发 | ❌ | ❌ | ✅ |

## 四阶段落地规划

### Phase 1: 夯实基础（第1-2周）
1. 转换质量报告(report_generator.py) — dm_converter已有ConversionResult.changes数据
2. 对象数量限制 — 社区版≤20对象
3. GUI修复(gui.py当前7行空壳)
4. pip打包(setup.py)
5. 落地页(GitHub Pages)

### Phase 2: 收费闭环（第3-4周）
1. License授权系统(license_manager.py, RSA签名+机器指纹)
2. 专业版功能隔离(功能开关)
3. 支付对接(支付宝当面付+对公转账)

### Phase 3: SaaS上线（第5-8周）
1. FastAPI后端(包装现有Python函数)
2. Web前端(上传→转换→下载+报告)
3. 部署上线(阿里云ECS+Nginx)

### Phase 4: 企业深耕（第9-16周）
1. Docker私有化版
2. 自定义规则DSL(YAML格式)
3. CSDN/达梦社区10篇引流文章
4. 达梦AI Agent(长期方向)

## 代码架构决策

**一套代码 + 功能开关，不分叉**

原因：
1. 分叉后改一个bug要改N份，一定遗漏
2. 开源代码里专业版功能"看得见但用不了"→本身就是广告
3. 开源社区贡献的bug修复自动惠及所有版本
4. 依赖图显示核心模块零外部依赖，增值模块可独立开关

实现：license_checker.py检查License等级，在增值模块入口处加gate.require('feature_name')

## 定价逻辑

- 项目买断¥2999是国内toB甜点(比手改便宜100倍，比外包便宜10倍)
- 信创场景天然需要付费(企业有预算、合规要求)
- dm_converter.py的深度规则是核心壁垒(新入者至少踩3个月坑)
