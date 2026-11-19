# CampusEvent —— 校园活动报名与管理系统

《软件工程》课程实验二项目。校园管理员发布活动，学生浏览并报名；系统用**策略模式**表达两类报名规则，用**观察者模式**把报名业务与站内通知解耦，并在需求变更后新增了**候补报名规则**与**邮件通知渠道**（见 `docs/需求变更影响分析.md`）。

- 技术栈：Python 3.10+ / Flask 3 / SQLite（标准库 `sqlite3`，无 ORM）
- 运行形态：单机 Web 应用，公网部署后浏览器直接访问
- 版本标签：`baseline-v1`（初始验收版本）、`change-v2`（需求变更完成版本）

---

## 1. 快速开始（从零运行）

```bash
# 1) 取得代码
git clone <你的仓库地址> 班级_学号_CampusEvent
cd 班级_学号_CampusEvent

# 2) 虚拟环境（Windows 用 python -m venv .venv 后执行 .venv\Scripts\activate）
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3) 初始化演示数据（--reset 会重建数据库）
python -m app.seed --reset

# 4) 启动
python run.py          # 开发/演示：http://127.0.0.1:5000
```

生产环境（云服务器）请使用 `deploy/` 下的脚本与配置，见第 8 节。

### 演示账号

| 角色 | 入口 | 账号 / 口令 |
| --- | --- | --- |
| 学生 A | `/login` 选择学号 | `S2024001` 张小明 |
| 学生 B | `/login` 选择学号 | `S2024002` 李小红 |
| 学生 C | `/login` 选择学号 | `S2024003` 王大力 |
| 管理员 | `/login` 管理员口令 | `admin123`（可用环境变量 `CAMPUS_ADMIN_CODE` 覆盖） |

> 课程环境使用固定演示账号，不实现注册与复杂权限系统（指导书附录 B.1）。所有口令/密钥都可以用环境变量覆盖，仓库内不含任何真实凭据。

### 演示数据

| 活动 | 报名规则 | 名额 | 用途 |
| --- | --- | --- | --- |
| 校园迎新晚会 | 直接报名 | 120 | 演示“名额充足→立即通过” |
| 程序设计马拉松（24h） | 审核报名 | 20 | 演示“提交待审核→管理员批准” |
| 摄影基础讲座 | 审核报名 | 3 | 名额小，便于现场演示“满员后不能批准” |
| 社区图书馆志愿服务 | 直接报名 | 15 | 演示取消报名后名额释放 |
| 校园歌手大赛（决赛） | 候补报名 | 2 | 演示“满员→候补第 N 位→有人取消后自动转正” |

---

## 2. 目录结构

```
班级_学号_CampusEvent/
├── app/
│   ├── __init__.py              # 应用工厂 + 依赖组合根（策略注册表、事件总线、通知服务）
│   ├── db.py                    # SQLite 连接、建表、事务边界、通知失败留痕
│   ├── repositories.py          # 仓储层（活动/学生/报名/消息/失败留痕）
│   ├── seed.py                  # 演示数据初始化
│   ├── domain/                  # 领域层（纯 Python，可脱离 Flask 单测）
│   │   ├── entities.py          # 实体与状态枚举
│   │   ├── errors.py            # 领域异常（中文用户提示）
│   │   ├── events.py            # 领域事件（报名提交/通过/拒绝/取消）
│   │   ├── event_bus.py         # 事件总线（观察者模式）
│   │   ├── policies.py          # 报名策略：抽象 + 两种实现 + 策略注册表
│   │   └── rules.py             # 名额规则（两类策略共享的公共规则）
│   ├── services/                # 业务服务（事务边界在这里）
│   │   ├── registration_service.py
│   │   ├── approval_service.py
│   │   ├── activity_service.py
│   │   └── notification_service.py   # 观察者：站内通知 + 邮件渠道（v2）
│   ├── web/routes.py            # 路由（只做参数校验/渲染/错误提示）
│   ├── templates/               # Jinja2 页面
│   └── static/style.css
├── tests/                       # pytest 用例（验收 T1–T17 + 设计单元测试 + v2 变更测试）
├── docs/                        # 设计材料与报告
├── deploy/                      # 云服务器部署脚本与配置
├── README.md
├── AI_DEV_LOG.md
└── requirements.txt
```

---

## 3. 需求与设计：关键决策

### 3.1 为什么用策略模式表达报名规则

报名流程中**稳定**的部分是：校验活动可报名 → 校验不可重复报名 → 落库 → 发通知。
**变化**的部分是“本次提交是立即通过，还是进入待审核”。因此：

- 抽象 `RegistrationPolicy.submit(context) -> PolicyDecision` 只回答准入问题；
- `DirectRegistrationPolicy` 立即 `approved`，`ApprovalRegistrationPolicy` 返回 `pending`；
- `PolicyRegistry` 依据 `activity.registration_mode` 选择实现，`RegistrationService` 里**没有任何 `if 活动类型 == ...` 的分支**；
- 需求变更新增的 `WaitlistRegistrationPolicy` 只需“新增一个类 + 注册一行”，主流程 0 改动（证据见变更分析文档）。

### 3.2 名额检查属于公共规则，检查时机属于策略

名额上限是活动自身的约束，与“要不要审核”无关，所以实现为无状态的 `CapacityRule`：

- 计数口径唯一：只统计 `approved`（待审核、已取消、已拒绝都不占名额）；
- 检查时机由策略决定：直接报名在提交时检查（满员直接拒绝）；审核报名在提交时不检查（可先进入待审核），在**管理员批准**时由 `ApprovalService` 调用同一条规则二次检查（满员不得再批准）。

这样避免了“两个策略各写一份名额判断”的重复，也避免把检查时机硬编码进主流程。

### 3.3 通知为什么用观察者模式，以及事务边界

- `RegistrationService` 只 `bus.publish(RegistrationSubmitted/…)`，不知道通知的存在；
- `NotificationService` 作为订阅者，把事件翻译为消息并投递到渠道；
- **事务边界**：报名记录先在自己的事务里提交，提交成功后才发布事件。因此通知失败**不会回滚**已经合法提交的报名；失败信息写入 `notification_failures` 表留痕（独立连接、独立事务），管理员后台可见；
- **避免重复通知**：`notifications(event_key, channel)` 上有唯一索引，同一业务事实（例如同一条报名记录的 `approved` 状态）重复投递会被 `INSERT OR IGNORE` 忽略。`event_key` 由事件类型 + 报名 ID（+状态）构成。

### 3.4 边界与异常处理

| 场景 | 处理 |
| --- | --- |
| 活动已开始 / 已下架 | 拒绝新增报名（`ActivityClosedError`），页面提示 |
| 同一学生同一活动重复报名 | 只允许一条“待审核/已通过”，数据库唯一索引 + 服务校验双保险 |
| 取消报名 | 仅本人可操作；释放名额并发送“报名已取消”通知 |
| 满员后批准 | 二次检查名额后拒绝，状态保持“待审核” |
| 管理员删除活动 | 采用**软删除**：活动从列表消失、不能报名，历史报名与通知全部保留，后台提示影响条数 |
| 通知渠道故障 | 逐渠道捕获 → 留痕 → 其他渠道继续；业务数据不受影响 |

---

## 4. 运行测试

```bash
python -m pytest -q              # 全量
python -m pytest tests/test_baseline.py -q   # 仅初始验收用例
python -m pytest -q --tb=short -k v2         # 仅需求变更新增用例
```

测试全部使用临时数据库（`tmp_path`），不会污染 `instance/`，可在任意机器复现。

---

## 5. 版本与 Git 标签

| 标签 | 含义 | 对应需求 |
| --- | --- | --- |
| `baseline-v1` | 初始验收版本 | 直接报名 + 审核报名两类规则；站内通知 |
| `change-v2` | 需求变更完成版本（在 v1 基础上新建分支实现） | 新增候补报名规则；新增邮件通知渠道；候补自动转正 |

```bash
git tag -l
git diff baseline-v1 change-v2 --stat     # 变更影响分析的客观依据
git checkout baseline-v1                  # 演示变更前版本
git checkout change-v2                     # 演示变更后版本
```

---

## 6. AI 参与说明

按指导书 1.3 节要求：AI 生成的设计与代码均视为待验证输出，全部结论以可复现的测试与手工验收为准；交付物中的每条验收结论都对应 `tests/` 中的可执行用例。关键提示词、设计决策与人工修正记录见 `AI_DEV_LOG.md`。

---

## 7. 提交材料索引

| 材料 | 位置 |
| --- | --- |
| 初始 SRS 分析 | `docs/SRS分析.md` |
| 用例说明（含用例图） | `docs/用例说明.md` |
| UML 类图（初版/变更版） | `docs/UML类图.md` + `docs/diagrams/*.png` |
| 时序图（报名、审批、候补转正） | `docs/时序图.md` + `docs/diagrams/*.png` |
| 设计模式决策报告 | `docs/设计模式决策报告.md` |
| 设计材料评审记录（他评签名） | `docs/设计评审记录.md` |
| 需求变更影响分析 | `docs/需求变更影响分析.md` |
| 回归测试表 | `docs/回归测试表.md` |
| AI 协作日志 | `AI_DEV_LOG.md` |
| 项目总结报告（5–8 页，Word） | `docs/实验报告.docx`（同目录 `.md` 为源文件） |
| 答辩 PPT | `docs/答辩PPT.pptx` |
| 运行截图（8 张） | `docs/screenshots/` |

---

## 8. 部署到云服务器（公网可访问）

前置：一台有公网 IP 的 Linux 云服务器（Ubuntu 22.04 / Debian 12 已验证），安全组放行 80 端口。

```bash
# 在服务器上
sudo apt update && sudo apt install -y python3-venv nginx git
git clone <你的仓库地址> /opt/campus-event && cd /opt/campus-event
sudo bash deploy/deploy.sh        # 建虚拟环境、装依赖、初始化数据库、装 systemd 服务
```

`deploy/deploy.sh` 会：
1. 创建 `/opt/campus-event/.venv` 并安装 `requirements.txt`；
2. 用 `python -m app.seed` 初始化 SQLite 数据库（默认 `instance/campus_event.db`）；
3. 安装 `campus-event.service`（waitress 4 进程，监听 `127.0.0.1:8000`）；
4. 安装 `nginx` 反代配置并 reload。

完成后访问 `http://<服务器公网IP>/` 即可。常用运维命令：

```bash
sudo systemctl status campus-event     # 状态
sudo journalctl -u campus-event -f     # 日志
sudo systemctl restart campus-event    # 重启
```

数据文件在 `/opt/campus-event/instance/campus_event.db`，备份直接复制该文件；邮件渠道的模拟发件落在 `/opt/campus-event/outbox/*.eml`。
