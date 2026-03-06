# Tabler Bootstrap 5 模板集成实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将现有的 Django 基础应用界面重构为基于 Tabler 的现代化企业级 Dashboard。

**Architecture:** 以纯静态资源方式（无构建管线）全量引入 Tabler 的预编译静态包，分步骤全面重写 Django 的 `base.html` 宏观布局和各独立 app 的视图模板。

**Tech Stack:** Django 6.0, Bootstrap 5, Tabler UI, HTML/CSS.

---

### Task 1: 获取并集成 Tabler 静态资源

**Files:**
- Create: `static/tabler/` (及下属的 css/js/fonts 目录)

**Step 1: 下载最新版 Tabler 预编译包**

利用终端下载解压 Tabler。由于无需构建，直接取其 dist 资源。

```bash
mkdir -p static/tabler/css static/tabler/js
# 这里我们假设通过 wget 或 curl 获取最新的 release 包
curl -fsSL https://github.com/tabler/tabler/releases/download/v1.0.0-beta20/tabler.zip -o tabler.zip
unzip -q tabler.zip -d dist-temp
cp -R dist-temp/css/* static/tabler/css/
cp -R dist-temp/js/* static/tabler/js/
rm -rf dist-temp tabler.zip
```

**Step 2: 验证静态资源目录结构**

运行命令：`ls -la static/tabler/css && ls -la static/tabler/js`
预期结果：看到 `tabler.min.css` 和 `tabler.min.js` 等核心文件。由于未涉及 Python 逻辑测试，此步骤仅验证文件获取成功。

**Step 3: Commit**

```bash
git add static/tabler/
git commit -m "chore: fetch and integrate tabler static assets"
```


### Task 2: 重构基础布局模板 (base.html)

**Files:**
- Modify: `templates/base.html`

**Step 1: 写入基础框架代码（带左侧边栏和顶栏）**

我们需要重写基础模板。在此步骤中移除原有的简单 Bootstrap 导航，引入完整的 Tabler HTML 框架：包含 `<aside class="navbar navbar-vertical...>` (侧边栏) 和 `<header class="navbar...">` (包含头像和消息的顶置导航栏)。

*(代码由于较长，在实际实施时通过 Edit 或 Write 工具写入具体文件。包含引入的静态文件标签 `<link rel="stylesheet" href="{% static 'tabler/css/tabler.min.css' %}">` 等)*

**Step 2: 启动本地服务器验证渲染**

运行命令检查静态文件解析是否有报错。

```bash
python manage.py check
```
预期：无语法错误抛出。实际上要在浏览器中刷新确认全局 CSS 是否已应用。由于采用 TDD 对模板重构有局限，此处采用服务器启动检查替代。

**Step 3: Commit**

```bash
git add templates/base.html
git commit -m "feat: refactor global base.html with clean tabler layout"
```


### Task 3: 改造主数据模块列表页 (Data App)

**Files:**
- Modify: `templates/data/product_list.html`
- Modify: `templates/data/color_list.html`
- (及其余 data 模块内的列表和表单页口)

**Step 1: 使用卡片和 Table 组件包裹数据**

将原先裸露的 `django-tables2` 或原生 Bootstrap 表格结构，重构为符合 Tabler 规范的 `card` 和 `table-responsive` 容器：

```html
<div class="card">
  <div class="card-header">
    <h3 class="card-title">产品列表</h3>
    <!-- 动作按钮如新增放在此处 -->
  </div>
  <div class="table-responsive">
    <table class="table card-table table-vcenter text-nowrap datatable">
       <!-- 原有循环变量填充 -->
    </table>
  </div>
</div>
```

**Step 2: 页面验证**

本地启动项目，并验证对应页面。确保不再有错乱的边距，表格与外层卡片完美融合。

**Step 3: Commit**

```bash
git add templates/data/
git commit -m "style: upgrade data app templates to tabler card components"
```


### Task 4: 改造排产计算结果页 (Schedule App)

**Files:**
- Modify: `templates/schedule/history.html`
- Modify: `templates/schedule/运算结果页` (如果有)

**Step 1: 引入数据仪表块 (Widgets)**

排产结果页通常信息量大，引入 Tabler 的进度条小组件和状态文本来展示（例如良率、进度百分比、各机器的占用率）。
将按钮升级为含有图标的块级操作按钮（如“导出 Excel”替换为带下载 SVG 图标的优雅按钮）。

**Step 2: 验证样式展示**

本地启动服务器预览排产结果结构。

**Step 3: Commit**

```bash
git add templates/schedule/
git commit -m "style: modernize schedule results and history view with widgets"
```


### Task 5: 优化账号与消息页面 (Accounts & Notifications)

**Files:**
- Modify: `templates/auth/login.html` (及其余账号相关页面)
- Modify: `templates/notifications/...`

**Step 1: 将登录页转为居中卡片**

将原有的登录/注册认证页改造成全屏居中、纯白背景卡的现代 SaaS 登录页风格。
通知列表重写为带未读/已读标识的优雅列表组（List Group）。

**Step 2: 界面渲染检查**

访问 `/login` 或相应的通知路由，确认布局没有因为全量引入的 css 导致组件塌陷。

**Step 3: Commit**

```bash
git add templates/auth/ templates/notifications/
git commit -m "style: refresh auth pages into centered saas layout"
```
