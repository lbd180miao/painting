# 涂装生产排程管理系统设计文档

**日期**: 2026-02-28
**项目**: 涂装双层滚动排产系统
**技术方案**: Django + Template

---

## 一、项目概述

### 1.1 目标
构建一个完整的涂装生产排程管理系统，实现数据导入、双层滚动排产算法计算、风险分析、历史记录管理等功能。

### 1.2 核心需求
- Excel数据导入（总成拉动数据、涂装库存、注塑库存、安全库存）
- 双层滚动排产算法（短期+长期）
- 阵型结构约束优化
- 风险分析与消息提醒
- 历史记录管理
- 参数配置（合格率、产能、约束等）
- 结果导出Excel
- 动态车型管理
- 简单登录验证

---

## 二、整体架构

### 2.1 架构图

```
涂装生产排程管理系统
│
├── 用户层
│   ├── 登录/登出
│   └── 权限控制（简单登录）
│
├── 功能模块
│   ├── 数据管理模块
│   │   ├── Excel数据导入（总成拉动、涂装库存、注塑库存、安全库存）
│   │   ├── 车型管理（动态添加车型、颜色）
│   │   └── 参数配置（合格率、产能百分比、约束参数等）
│   │
│   ├── 排产计算模块
│   │   ├── 短期需求计算
│   │   ├── 长期需求计算
│   │   ├── 风险分析（短期/长期）
│   │   ├── 短期计划生成
│   │   ├── 长期计划生成
│   │   └── 阵型约束优化
│   │
│   ├── 结果展示模块
│   │   ├── 提前期需求表（短期/长期）
│   │   ├── 风险表（短期/长期）
│   │   ├── 生产计划表（短期/长期）
│   │   ├── 阵型排布图
│   │   └── 库存更新预览
│   │
│   ├── 历史记录模块
│   │   ├── 排产历史列表
│   │   ├── 历史详情查看
│   │   └── 历史数据导出
│   │
│   └── 系统管理模块
│       ├── 用户管理
│       ├── 站内消息提醒
│       └── 数据导出
│
└── 数据层
    ├── 原始数据（导入的Excel数据）
    ├── 计算结果（排产计划）
    ├── 历史记录
    ├── 配置参数
    └── 用户消息
```

### 2.2 技术架构
- 采用经典的MVT架构（Model-View-Template）
- 使用Django ORM进行数据持久化
- 计算模块封装为独立服务类
- 前端使用Bootstrap进行样式美化

---

## 三、数据模型设计

### 3.1 核心数据表

| 表名 | 说明 | 主要字段 |
|------|------|----------|
| User | 用户 | 用户名、密码 |
| VehicleModel | 车型 | name (A0, A1) |
| Color | 颜色 | name |
| PositionType | 前后位置 | name (front/rear) |
| Product | 产品 | vehicle_model, color, position_type, yield_rate |
| Inventory | 涂装库存 | product, current_quantity, updated_quantity |
| InjectionInventory | 注塑库存 | product, current_quantity, updated_quantity |
| SafetyStock | 安全库存 | product, quantity |
| AssemblyPullData | 总成拉动数据 | sequence, vehicle_model, color, planned_time |
| SystemParameter | 系统参数 | param_key, param_value, description |
| ScheduleRecord | 排产记录 | record_time, short_term_duration, long_term_duration |
| SchedulePlan | 排产计划详情 | record, product, plan_type, vehicle_count |
| FormationSlot | 阵型槽位 | record, slot_number, product, plan_type |
| RiskRecord | 风险记录 | record, product, risk_type, final_value, risk_value |
| Message | 站内消息 | user, title, content, is_read |

### 3.2 关键系统参数

| 参数键 | 默认值 | 说明 |
|--------|--------|------|
| CYCLE_TIME_MIN | 300 | 涂装一圈时间（分钟） |
| AVG_HANGING_COUNT | 4 | 每车平均挂数 |
| TOTAL_VEHICLES | 100 | 涂装线一圈车数 |
| SHORT_TERM_CAPACITY | 40 | 短期产能百分比（%） |
| LONG_TERM_CAPACITY | 60 | 长期产能百分比（%） |
| FRONT_REAR_BALANCE_D | 15 | 前后平衡约束差值 |
| GROUP_CAPACITY_LIMIT | 40 | 组车数平衡约束（%） |
| LONG_TERM_FORECAST_HOURS | 2 | 长期需求预测时间（小时） |

---

## 四、排产算法设计

### 4.1 计算流程

```
class SchedulingAlgorithm:
    def calculate(input_data):
        # Step 1: 读取基础数据
        data = load_base_data(input_data)

        # Step 2: 生成提前期需求
        short_term = calculate_short_term_demand(data)
        long_term = calculate_long_term_demand(data)

        # Step 3: 计算短期风险表
        short_risk = calculate_short_term_risk(data, short_term)

        # Step 4: 计算长期风险表
        long_risk = calculate_long_term_risk(data, long_term)

        # Step 5: 计算短期计划表
        short_plan = calculate_short_term_plan(data, short_risk)

        # Step 6: 计算长期计划表
        long_plan = calculate_long_term_plan(data, long_risk)

        # Step 7: 阵型结构约束优化
        formation = optimize_formation(short_plan, long_plan)

        # Step 8: 延迟更新库存
        updated_inventory = update_inventory(formation)

        # Step 9: 检查风险并发送提醒
        check_and_notify_risk(short_risk, long_risk)

        return results
```

### 4.2 核心计算公式

1. **短期需求数量** = 涂装线一圈车数 × 每车平均挂数 × 短期产能百分比 / 2

2. **长期需求数量** = 涂装线一圈车数 × 每车平均挂数 × 长期产能百分比 / 2

3. **生产数量** = 需求数量 / 合格率（向上取整）

4. **短期终值** = 当前库存 - 短期需求生产数量

5. **长期终值** = 当前库存 - 长期需求生产数量

6. **风险值** = 安全库存 - 长期终值

7. **组风险** = max(front风险, rear风险)

### 4.3 产品挂具配置

| 产品 | 每车件数 | 合格率 |
|------|----------|--------|
| A0 front | 5 | 80% |
| A0 rear | 5 | 80% |
| A1 front | 4 | 90% |
| A1 rear | 4 | 90% |

---

## 五、URL结构与页面设计

### 5.1 URL结构

| 路径 | 功能 |
|------|------|
| / | 仪表板首页 |
| /data/import/ | 数据导入页面 |
| /data/inventory/ | 涂装库存管理 |
| /data/injection/ | 注塑库存管理 |
| /data/safety/ | 安全库存管理 |
| /data/assembly/ | 总成拉动数据管理 |
| /config/vehicles/ | 车型管理 |
| /config/colors/ | 颜色管理 |
| /config/products/ | 产品管理 |
| /config/parameters/ | 系统参数配置 |
| /schedule/calculate/ | 执行排产计算 |
| /schedule/result/<id>/ | 查看计算结果 |
| /history/list/ | 排产历史列表 |
| /history/detail/<id>/ | 历史详情 |
| /auth/login/ | 登录 |
| /auth/logout/ | 登出 |
| /messages/ | 站内消息 |
| /export/<id>/ | 导出Excel |

### 5.2 页面布局
- 顶部导航栏（Logo + 主菜单 + 消息提醒 + 用户信息）
- 左侧侧边栏（子菜单）
- 主内容区（表格、表单、结果展示）

---

## 六、技术栈选型

### 6.1 后端技术栈
- Django 6.0.2
- Python 3.10+
- SQLite (开发) / PostgreSQL (生产)
- pandas (数据处理)
- openpyxl (Excel操作)
- Celery + Redis (异步任务，可选)

### 6.2 前端技术栈
- Django Template
- Bootstrap 5
- 原生JS + jQuery
- DataTables (表格交互)
- Chart.js 或 ECharts (图表，可选)

### 6.3 Python依赖包
```
django-bootstrap5
pandas
openpyxl
openpyxl-styled
django-extensions
django-debug-toolbar
python-dotenv
```

---

## 七、错误处理与数据校验

### 7.1 数据导入校验
- Excel文件格式校验
- 列名匹配（支持模糊匹配）
- 数据类型校验
- 必填字段检查

### 7.2 业务数据校验
- 库存数量非负
- 合格率范围（0-100%）
- 产能百分比范围（0-100%）
- 车型颜色存在性检查

### 7.3 错误处理
- 友好的错误提示
- 具体定位错误位置
- 计算日志记录
- 事务回滚保证

---

## 八、测试策略

### 8.1 测试层级
1. **单元测试** - 算法函数、数据校验
2. **集成测试** - 完整流程测试
3. **UI测试** - 页面交互测试

### 8.2 测试覆盖率目标
- 核心算法模块: 90%+
- 数据处理模块: 80%+
- 整体: 70%+

---

## 九、部署与维护

### 9.1 生产环境
- 数据库: PostgreSQL
- Web服务器: Nginx + Gunicorn
- 静态文件: WhiteNoise
- 环境变量: python-dotenv

### 9.2 数据备份
- 数据库定期自动备份
- Excel文件存档
- 排产历史保留
- 支持数据导出

---

## 十、开发阶段划分

### 第一阶段：基础框架 + 数据管理
- 用户登录
- 数据导入功能
- 车型配置
- 参数配置

### 第二阶段：核心算法
- 短期/长期需求计算
- 风险分析
- 计划生成
- 阵型优化

### 第三阶段：结果展示与历史
- 结果展示页面
- 历史记录管理
- 数据导出
- 消息提醒

### 第四阶段：完善与优化
- 测试与修复
- 性能优化
- 用户体验优化
