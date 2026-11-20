"""生成答辩用 PPT：docs/答辩PPT.pptx

用法：python tools/build_ppt.py
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Emu, Pt

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SHOTS = DOCS / "screenshots"
DIAG = DOCS / "diagrams"
OUT = DOCS / "答辩PPT.pptx"

INK = RGBColor(0x1F, 0x2A, 0x44)
MUTED = RGBColor(0x6B, 0x73, 0x84)
ACCENT = RGBColor(0x2F, 0x6B, 0xFF)
LIGHT = RGBColor(0xEE, 0xF2, 0xFF)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
SUCCESS = RGBColor(0x1B, 0x9C, 0x6B)
WARN = RGBColor(0xC2, 0x41, 0x2E)
FONT = "微软雅黑"

W, H = Emu(12192000), Emu(6858000)  # 16:9


def blank(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def textbox(slide, left, top, width, height, size=18, color=INK, bold=False,
            align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, line_spacing=1.2):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.paragraphs[0].alignment = align
    tf.paragraphs[0].line_spacing = line_spacing
    run = tf.paragraphs[0].add_run()
    run.text = ""
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.font.bold = bold
    run.font.name = FONT
    return tf


def write(tf, text, size=None, color=None, bold=None, bullet=False, space_before=6):
    first = tf.paragraphs[0]
    if len(tf.paragraphs) == 1 and first.text.strip() == "":
        para = first
    else:
        para = tf.add_paragraph()
        para.space_before = Pt(space_before)
    para.line_spacing = 1.25
    run = para.add_run()
    run.text = ("· " if bullet else "") + text
    if size:
        run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = color
    if bold is not None:
        run.font.bold = bold
    run.font.name = FONT
    return para


def band(slide, color=LIGHT, top=Emu(0), height=Emu(700000)):
    shape = slide.shapes.add_shape(1, Emu(0), top, W, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    return shape


def header(slide, title, kicker=None):
    band(slide, LIGHT, Emu(0), Emu(980000))
    tf = textbox(slide, Emu(700000), Emu(150000), Emu(10000000), Emu(500000), 26, INK, True)
    write(tf, title, 26, INK, True)
    if kicker:
        tf2 = textbox(slide, Emu(700000), Emu(600000), Emu(10000000), Emu(320000), 11.5, MUTED)
        write(tf2, kicker, 11.5, MUTED)
    line = slide.shapes.add_shape(1, Emu(700000), Emu(1040000), Emu(10800000), Emu(20000))
    line.fill.solid()
    line.fill.fore_color.rgb = ACCENT
    line.line.fill.background()


def page_no(slide, idx, total):
    tf = textbox(slide, Emu(10800000), Emu(6250000), Emu(900000), Emu(300000), 11, MUTED,
                 align=PP_ALIGN.RIGHT)
    write(tf, f"{idx}/{total}", 11, MUTED)


def card(slide, left, top, width, height, fill=WHITE, line_color=RGBColor(0xDD, 0xE3, 0xF0)):
    shape = slide.shapes.add_shape(5, left, top, width, height)  # rounded rect
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.color.rgb = line_color
    shape.line.width = Pt(0.75)
    return shape


def picture(slide, path: Path, left, top, max_w, max_h):
    from PIL import Image  # 已随 python-pptx 依赖安装

    with Image.open(path) as im:
        pw, ph = im.size
    ratio = min(max_w / pw, max_h / ph)
    w, h = int(pw * ratio), int(ph * ratio)
    return slide.shapes.add_picture(str(path), int(left), int(top), int(w), int(h))


def table(slide, rows, left, top, width, height, font=12, header_fill=ACCENT):
    shape = slide.shapes.add_table(len(rows), len(rows[0]), left, top, width, height).table
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = shape.cell(i, j)
            cell.text = ""
            para = cell.text_frame.paragraphs[0]
            run = para.add_run()
            run.text = str(val)
            run.font.size = Pt(font)
            run.font.name = FONT
            run.font.bold = i == 0
            run.font.color.rgb = WHITE if i == 0 else INK
            para.line_spacing = 1.0
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            cell.fill.fore_color.rgb = header_fill if i == 0 else (LIGHT if i % 2 == 0 else WHITE)
    return shape


def build():
    prs = Presentation()
    prs.slide_width, prs.slide_height = W, H
    total = 15

    # 1 封面
    s = blank(prs)
    bg = s.shapes.add_shape(1, Emu(0), Emu(0), W, H)
    bg.fill.solid()
    bg.fill.fore_color.rgb = INK
    bg.line.fill.background()
    accent = s.shapes.add_shape(1, Emu(0), Emu(0), Emu(180000), H)
    accent.fill.solid()
    accent.fill.fore_color.rgb = ACCENT
    accent.line.fill.background()

    tf = textbox(s, Emu(1100000), Emu(1900000), Emu(9800000), Emu(900000), 14, RGBColor(0x9C, 0xB2, 0xE0))
    write(tf, "《软件工程》实验二 · 答辩", 14, RGBColor(0x9C, 0xB2, 0xE0))
    tf = textbox(s, Emu(1100000), Emu(2350000), Emu(10000000), Emu(1400000), 40, WHITE, True)
    write(tf, "基于设计模式的校园活动报名与管理系统", 40, WHITE, True)
    tf = textbox(s, Emu(1100000), Emu(3500000), Emu(10000000), Emu(500000), 18, RGBColor(0xC7, 0xD3, 0xEA))
    write(tf, "CampusEvent：策略模式表达报名规则 · 观察者模式解耦通知 · 需求变更不改主流程", 18,
          RGBColor(0xC7, 0xD3, 0xEA))
    tf = textbox(s, Emu(1100000), Emu(4500000), Emu(10000000), Emu(600000), 13, RGBColor(0x8F, 0xA4, 0xCE))
    write(tf, "宋木荣　　计科 2 班　　学号 217　　2026 年 11 月", 13, RGBColor(0x8F, 0xA4, 0xCE))
    for i, (k, v) in enumerate([("2", "个版本标签"), ("3", "种报名规则"), ("30", "项测试全通过")]):
        x = Emu(1100000 + i * 2600000)
        card(s, x, Emu(5300000), Emu(2300000), Emu(900000), RGBColor(0x2A, 0x36, 0x52),
             RGBColor(0x3C, 0x4C, 0x70))
        tf = textbox(s, x + Emu(160000), Emu(5420000), Emu(2000000), Emu(500000), 22, WHITE, True)
        write(tf, k, 22, WHITE, True)
        tf = textbox(s, x + Emu(160000), Emu(5900000), Emu(2000000), Emu(300000), 11,
                     RGBColor(0x9C, 0xB2, 0xE0))
        write(tf, v, 11, RGBColor(0x9C, 0xB2, 0xE0))

    # 2 目标与范围
    s = blank(prs)
    header(s, "实验目标与范围：用可量化的证据证明“可扩展”", "对应指导书 3.1–3.7")
    left, top, wd = Emu(700000), Emu(1250000), Emu(5200000)
    card(s, left, top, wd, Emu(4300000))
    tf = textbox(s, left + Emu(300000), top + Emu(250000), wd - Emu(600000), Emu(3800000), 13)
    write(tf, "四个必须交付的成果", 15, ACCENT, True)
    for item in [
        "一套能表达三种报名规则（直接 / 审核 / 候补）的领域模型",
        "报名与通知松耦合，通知失败不破坏业务事实",
        "两个可比对版本：baseline-v1 与 change-v2，差异用 git 量化",
        "可运行 Web 系统 + 可复现测试 + 真实截图证据",
    ]:
        write(tf, item, 13, INK, bullet=True, space_before=10)
    write(tf, "明确不做（控制范围）", 15, WARN, True, space_before=18)
    write(tf, "注册与找回密码、复杂权限体系、支付、真实短信、并发压测", 13, MUTED)

    left2 = Emu(6300000)
    card(s, left2, top, Emu(5200000), Emu(4300000))
    tf = textbox(s, left2 + Emu(300000), top + Emu(250000), Emu(4600000), Emu(3800000), 13)
    write(tf, "技术与分层", 15, ACCENT, True)
    for item in [
        "Flask 3 + 标准库 sqlite3（无 ORM）",
        "分层：web → services → domain ← repositories",
        "领域层不依赖 Flask，可被 pytest 直接驱动",
        "事务边界在服务层；异常即不变量",
        "部署：waitress + nginx，deploy/ 一键脚本",
    ]:
        write(tf, item, 13, INK, bullet=True, space_before=10)
    tf = textbox(s, left2 + Emu(300000), top + Emu(3100000), Emu(4600000), Emu(1000000), 12, MUTED)
    write(tf, "演示账号：S2024001/2/3；管理员口令 admin123", 12, MUTED)
    page_no(s, 2, total)

    # 3 设计模式 A 策略
    s = blank(prs)
    header(s, "设计模式 A：策略模式承载“报名规则”", "稳定的是流程，变化的是“本次提交的结论”")
    rows = [
        ["规则", "策略实现", "submit 的结论", "名额检查时机"],
        ["直接报名", "DirectRegistrationPolicy", "approved（有名额）/ 拒绝", "提交时"],
        ["审核报名", "ApprovalRegistrationPolicy", "pending", "批准时（ApprovalService）"],
        ["候补报名（v2）", "WaitlistRegistrationPolicy", "approved / waitlisted + queue_no", "提交时"],
    ]
    table(s, rows, Emu(700000), Emu(1250000), Emu(10900000), Emu(2100000), 12)
    tf = textbox(s, Emu(700000), Emu(3600000), Emu(5200000), Emu(2300000), 13)
    write(tf, "抽象只回答一个问题", 15, ACCENT, True)
    write(tf, "submit(context) → PolicyDecision(status, message, queue_no)", 12, INK, bold=True)
    write(tf, "message 由策略给出，避免上层再拼装业务语义；queue_no 在 v1 预留，v2 恰好被用到。", 12, MUTED)
    card(s, Emu(6300000), Emu(3550000), Emu(5200000), Emu(2300000), RGBColor(0x0F, 0x1A, 0x2E))
    tf = textbox(s, Emu(6520000), Emu(3700000), Emu(4800000), Emu(2000000), 11,
                 RGBColor(0xD6, 0xE0, 0xF5))
    write(tf, "policy = registry.for_mode(activity.registration_mode)", 11, RGBColor(0x9E, 0xE0, 0xC0))
    write(tf, "decision = policy.submit(ctx)", 11, RGBColor(0xD6, 0xE0, 0xF5))
    write(tf, "# 主流程里没有任何 if 活动类型", 11, RGBColor(0x8B, 0x9B, 0xB8))
    write(tf, "record = repo.create(..., status=decision.status)", 11, RGBColor(0xD6, 0xE0, 0xF5))
    page_no(s, 3, total)

    # 4 名额归属
    s = blank(prs)
    header(s, "核心判断：名额口径是公共规则，检查时机属于策略", "本实验最关键的一次设计取舍")
    left, top = Emu(700000), Emu(1250000)
    card(s, left, top, Emu(5100000), Emu(3000000), RGBColor(0xE9, 0xF6, 0xF0), RGBColor(0xC7, 0xE9, 0xD8))
    tf = textbox(s, left + Emu(300000), top + Emu(220000), Emu(4500000), Emu(2600000), 13)
    write(tf, "采纳的方案", 15, SUCCESS, True)
    for item in [
        "CapacityRule 无状态，只统计 approved",
        "待审核 / 已取消 / 已拒绝 / 候补都不占名额",
        "口径只有一份，避免三个策略各写一遍 COUNT",
        "谁调用它由策略决定：提交时 / 批准时",
    ]:
        write(tf, item, 13, INK, bullet=True, space_before=8)
    card(s, Emu(6100000), top, Emu(5400000), Emu(3000000), RGBColor(0xFD, 0xEF, 0xEC), RGBColor(0xF3, 0xC9, 0xC1))
    tf = textbox(s, Emu(6400000), top + Emu(220000), Emu(4800000), Emu(2600000), 13)
    write(tf, "被拒绝的方案（AI 首轮建议）", 15, WARN, True)
    for item in [
        "把名额检查全部放进 RegistrationService",
        "后果：服务必须知道“哪条规则要查名额”",
        "等于把策略语义搬回主流程，新增规则必然改服务",
        "审核型活动会在提交阶段就占名额（业务错误）",
    ]:
        write(tf, item, 13, INK, bullet=True, space_before=8)
    tf = textbox(s, Emu(700000), Emu(4500000), Emu(10800000), Emu(1400000), 14, INK)
    write(tf, "验收证据：T2 / T3 / T5 / D3 —— 满员拒绝、待审核不占额、满员不得再批准、名额只计已通过。", 14, INK, True)
    page_no(s, 4, total)

    # 5 观察者
    s = blank(prs)
    header(s, "设计模式 B：观察者模式解耦报名与通知", "业务只发事件，通知是订阅者；失败不回滚业务")
    steps = [
        ("1", "业务事务", "BEGIN → INSERT → COMMIT\n报名记录先落库"),
        ("2", "发布事件", "bus.publish(RegistrationSubmitted)\n服务不认识通知"),
        ("3", "订阅者", "NotificationService.handle\n+ v2 转正服务"),
        ("4", "渠道投递", "inapp / email\n唯一索引去重"),
    ]
    for i, (num, name, desc) in enumerate(steps):
        x = Emu(700000 + i * 2700000)
        card(s, x, Emu(1300000), Emu(2450000), Emu(1700000))
        tf = textbox(s, x + Emu(200000), Emu(1400000), Emu(2100000), Emu(300000), 12, ACCENT, True)
        write(tf, num, 12, ACCENT, True)
        tf = textbox(s, x + Emu(200000), Emu(1700000), Emu(2100000), Emu(300000), 14, INK, True)
        write(tf, name, 14, INK, True)
        tf = textbox(s, x + Emu(200000), Emu(2050000), Emu(2100000), Emu(900000), 11, MUTED)
        write(tf, desc, 11, MUTED)
    rows = [
        ["问题", "设计回答", "证据"],
        ["通知失败要不要回滚报名", "不回滚：事务先提交，失败写 notification_failures", "T11"],
        ["重复事件会不会重复通知", "(event_key, channel) 唯一索引 + INSERT OR IGNORE", "T12 / V3"],
        ["订阅者异常会不会影响其他订阅者", "EventBus 逐订阅者 try/except + error_listener", "D4"],
    ]
    table(s, rows, Emu(700000), Emu(3300000), Emu(10900000), Emu(1900000), 12)
    tf = textbox(s, Emu(700000), Emu(5450000), Emu(10800000), Emu(600000), 12, MUTED)
    write(tf, "代价：事件顺序成为隐式契约。本项目用“转正后单独发一条通知”规避顺序依赖，而不是依赖订阅注册顺序。", 12, MUTED)
    page_no(s, 5, total)

    # 6 类图 v1
    s = blank(prs)
    header(s, "初版 UML 类图（baseline-v1）", "依赖单向，无循环：service → 策略抽象 / 事件总线")
    pic = picture(s, DIAG / "class-baseline-v1.png", Emu(500000), Emu(1200000), Emu(11200000), Emu(5100000))
    page_no(s, 6, total)

    # 7 变更
    s = blank(prs)
    header(s, "需求变更：两条 CR，三种机制吸收", "CR-01 候补规则 + 自动转正　/　CR-02 邮件通知渠道")
    rows = [
        ["变更", "吸收机制", "改动落点", "主流程分支"],
        ["CR-01 候补入队", "策略槽位", "新增 WaitlistRegistrationPolicy（36 行）", "0 处新增"],
        ["CR-01 取消后转正", "事件订阅位", "新增 WaitlistPromotionService（76 行）", "cancel() 一行未改"],
        ["CR-01 位次存储", "数据迁移", "queue_no 列 + 唯一索引扩展到 waitlisted", "—"],
        ["CR-02 邮件渠道", "渠道接口", "NotificationChannel + EmailChannel，通知服务渠道化", "—"],
    ]
    table(s, rows, Emu(700000), Emu(1250000), Emu(10900000), Emu(2300000), 11.5)
    left, top = Emu(700000), Emu(3800000)
    card(s, left, top, Emu(5100000), Emu(2200000), RGBColor(0xFD, 0xEF, 0xEC), RGBColor(0xF3, 0xC9, 0xC1))
    tf = textbox(s, left + Emu(300000), top + Emu(200000), Emu(4500000), Emu(1900000), 12)
    write(tf, "唯一“必要重构”：NotificationService", 13, WARN, True)
    write(tf, "baseline 把“写站内信”写死在一个方法里，属于过早具体化；", 12, INK)
    write(tf, "渠道化改造 +69 行，是这次变更最值得记录的教训。", 12, INK)
    card(s, Emu(6100000), top, Emu(5400000), Emu(2200000), RGBColor(0xE9, 0xF6, 0xF0), RGBColor(0xC7, 0xE9, 0xD8))
    tf = textbox(s, Emu(6400000), top + Emu(200000), Emu(4800000), Emu(1900000), 12)
    write(tf, "改了但没“打穿”", 13, SUCCESS, True)
    write(tf, "RegistrationService 仅 +8/−2 行：按结果状态选择事件类型；", 12, INK)
    write(tf, "领域规则 rules.py、审批服务、域错误均未改动。", 12, INK)
    page_no(s, 7, total)

    # 8 类图 v2
    s = blank(prs)
    header(s, "变更版 UML 类图（change-v2）", "新增 4 个类、2 个事件、1 个字段；依赖方向不变")
    pic = picture(s, DIAG / "class-change-v2.png", Emu(500000), Emu(1200000), Emu(11200000), Emu(5100000))
    page_no(s, 8, total)

    # 9 时序图
    s = blank(prs)
    header(s, "时序图：候补入队与自动转正", "取消事件被两个订阅者消费，转正同样“先提交事务再发事件”")
    picture(s, DIAG / "seq-waitlist.png", Emu(650000), Emu(1180000), Emu(10900000), Emu(3800000))
    keys = [
        ("满员即入队", "策略只负责入队与位次，不改主流程"),
        ("开始后不转正", "转正前判断 activity.is_open（V5）"),
        ("FIFO 顺序", "由 queue_no 决定，不看插入时间（V6）"),
        ("转正也发事件", "RegistrationPromoted → 通知 + 邮件"),
    ]
    for i, (k, v) in enumerate(keys):
        x = Emu(700000 + i * 2750000)
        card(s, x, Emu(5150000), Emu(2550000), Emu(900000))
        tf = textbox(s, x + Emu(180000), Emu(5230000), Emu(2200000), Emu(300000), 10.5, ACCENT, True)
        write(tf, k, 10.5, ACCENT, True)
        tf = textbox(s, x + Emu(180000), Emu(5560000), Emu(2200000), Emu(500000), 9.5, MUTED)
        write(tf, v, 9.5, MUTED)
    page_no(s, 9, total)

    # 10 影响指标
    s = blank(prs)
    header(s, "变更影响指标（客观数据，来自 git 与 pytest）", "git diff --stat baseline-v1 change-v2")
    rows = [
        ["指标", "数值", "说明"],
        ["app/ 源码改动", "16 文件 +394 / −42 行", "含模板与样式；测试另 +173 行"],
        ["新增类 / 接口", "4", "候补策略、转正服务、邮件渠道、渠道接口"],
        ["新增领域事件", "2", "RegistrationWaitlisted / RegistrationPromoted"],
        ["修改核心业务类", "2", "NotificationService +69；RegistrationService +8/−2"],
        ["主流程新增条件分支", "0", "register() 中仍无 if 活动类型"],
        ["回归失败数", "0 / 30", "pytest -q 全绿"],
        ["AI 交互轮次 / 变更耗时", "9 / 约 1.5 小时", "见 AI_DEV_LOG.md（M1–M9）"],
    ]
    table(s, rows, Emu(700000), Emu(1250000), Emu(10900000), Emu(3900000), 12)
    tf = textbox(s, Emu(700000), Emu(5400000), Emu(10800000), Emu(700000), 12, MUTED)
    write(tf, "对照：从零实现 baseline 约 4 小时；变更仅 1.5 小时（含迁移与 3 次缺陷修复）。", 12, MUTED)
    page_no(s, 10, total)

    # 11 测试
    s = blank(prs)
    header(s, "测试结果：30 项全通过，回归零失败", "python -m pytest -q　（每例独立临时库）")
    tf = textbox(s, Emu(700000), Emu(1250000), Emu(3000000), Emu(700000), 40, SUCCESS, True)
    write(tf, "30 passed", 40, SUCCESS, True)
    tf = textbox(s, Emu(700000), Emu(1950000), Emu(3000000), Emu(400000), 12, MUTED)
    write(tf, "约 1.3 秒；失败 0", 12, MUTED)
    rows = [
        ["测试组", "数量", "覆盖", "结果"],
        ["基线功能 T1–T17", "17", "三类报名、名额、取消、非法审批、软删除、通知失败留痕、幂等、持久化、HTTP 全流程", "通过"],
        ["设计契约 D1–D5", "5", "策略注册、语义差异、名额只计已通过、订阅者故障隔离、截止边界", "通过"],
        ["变更验证 V1–V8", "8", "候补入队与位次、取消转正、邮件落盘去重、候补唯一、开始后不转正、FIFO、三模式、页面可见", "通过"],
    ]
    table(s, rows, Emu(3900000), Emu(1250000), Emu(7700000), Emu(2800000), 10.5)
    card(s, Emu(700000), Emu(4500000), Emu(10900000), Emu(1400000), RGBColor(0xFD, 0xF6, 0xE7),
         RGBColor(0xEE, 0xD9, 0xA8))
    tf = textbox(s, Emu(950000), Emu(4620000), Emu(10300000), Emu(1200000), 11.5)
    write(tf, "未覆盖项（如实说明）：并发抢名额（SQLite 单进程、未做压测）、真实 SMTP 投递、角色越权测试（当前为演示级口令）。", 11.5, INK)
    page_no(s, 11, total)

    # 12 截图
    s = blank(prs)
    header(s, "运行截图：三种规则、候补转正、邮件投递证据", "实机运行，非合成")
    from PIL import Image

    def crop(name, box):
        dst_dir = DOCS / "_build"
        dst_dir.mkdir(exist_ok=True)
        with Image.open(SHOTS / name) as im:
            im.crop(box).save(dst_dir / name)
        return dst_dir / name

    big = crop("06_promotion.png", (70, 75, 1240, 790))
    small1 = crop("03_waitlist.png", (70, 40, 1240, 760))
    small2 = crop("08_admin_channels.png", (70, 320, 1240, 900))

    # 左：取消后自动转正（大幅）
    card(s, Emu(560000), Emu(1220000), Emu(6250000), Emu(4300000))
    picture(s, big, Emu(640000), Emu(1300000), Emu(6100000), Emu(3300000))
    tf = textbox(s, Emu(640000), Emu(4680000), Emu(6100000), Emu(700000), 11, INK, True)
    write(tf, "张小明取消 → 名额释放，王大力（候补第 1 位）自动转正，已通过名单变为李小红 + 王大力", 11, INK, True)

    # 右：两张小图上下排
    card(s, Emu(6950000), Emu(1220000), Emu(4600000), Emu(2080000))
    picture(s, small1, Emu(7030000), Emu(1290000), Emu(4440000), Emu(1560000))
    tf = textbox(s, Emu(7030000), Emu(2880000), Emu(4440000), Emu(350000), 10, INK, True)
    write(tf, "满员 2/2 → 王大力进入候补队列第 1 位", 10, INK, True)

    card(s, Emu(6950000), Emu(3430000), Emu(4600000), Emu(2090000))
    picture(s, small2, Emu(7030000), Emu(3500000), Emu(4440000), Emu(1560000))
    tf = textbox(s, Emu(7030000), Emu(5090000), Emu(4440000), Emu(350000), 10, INK, True)
    write(tf, "后台：候补列 + outbox 中的 .eml 投递证据", 10, INK, True)
    page_no(s, 12, total)

    # 13 三个问题
    s = blank(prs)
    header(s, "开发中真实遇到的三个问题", "没有一条是“一次写对”的")
    items = [
        ("候补重复报名抛数据库异常", "find_active 的状态集合漏了 waitlisted，业务校验被绕过，最终撞唯一索引。",
         "修正查询口径，而非捕获异常掩盖"),
        ("邮件记录被当成学生消息", "list_for_student 未按渠道过滤，未读角标翻倍。",
         "查询默认 channel='inapp'，三处同步"),
        ("断言“通过”了但其实写错", "断言“报名成功”，实际文案是“成功报名”。",
         "解码后断言真实文案 + 校验 .eml 产物"),
    ]
    for i, (title, cause, fix) in enumerate(items):
        y = Emu(1250000 + i * 1500000)
        card(s, Emu(700000), y, Emu(10900000), Emu(1300000))
        tf = textbox(s, Emu(950000), y + Emu(120000), Emu(10200000), Emu(300000), 13, WARN, True)
        write(tf, f"{i+1}. {title}", 13, WARN, True)
        tf = textbox(s, Emu(950000), y + Emu(480000), Emu(7300000), Emu(700000), 11.5, INK)
        write(tf, cause, 11.5, INK)
        tf = textbox(s, Emu(8300000), y + Emu(450000), Emu(3300000), Emu(700000), 11, SUCCESS, True)
        write(tf, "修复：" + fix, 11, SUCCESS, True)
    tf = textbox(s, Emu(700000), Emu(5950000), Emu(10800000), Emu(500000), 11.5, MUTED)
    write(tf, "共同教训：变更时不仅要改“产生状态的代码”，还要盘点“读状态的查询”；同一张表承载两种语义时，必须用默认值强制约束。", 11.5, MUTED)
    page_no(s, 13, total)

    # 14 结论
    s = blank(prs)
    header(s, "结论与反思", "机制有效，代价也要说清楚")
    left, top = Emu(700000), Emu(1250000)
    card(s, left, top, Emu(5100000), Emu(4300000), RGBColor(0xE9, 0xF6, 0xF0), RGBColor(0xC7, 0xE9, 0xD8))
    tf = textbox(s, left + Emu(300000), top + Emu(220000), Emu(4500000), Emu(3900000), 12.5)
    write(tf, "成立的地方", 15, SUCCESS, True)
    for item in [
        "变更被三种机制吸收：策略槽位、事件订阅位、渠道接口",
        "回归 30/30 通过，核心类仅改 8~69 行",
        "每个关键结论都有测试编号对应",
        "AI 的 4 次建议被人工否决并记入日志",
    ]:
        write(tf, item, 12.5, INK, bullet=True, space_before=10)
    card(s, Emu(6100000), top, Emu(5400000), Emu(4300000), RGBColor(0xFD, 0xEF, 0xEC), RGBColor(0xF3, 0xC9, 0xC1))
    tf = textbox(s, Emu(6400000), top + Emu(220000), Emu(4800000), Emu(3900000), 12.5)
    write(tf, "付出的代价", 15, WARN, True)
    for item in [
        "调用链变长：一次报名穿过 7 个对象",
        "NotificationService 渠道化是必要重构，暴露 baseline 过早具体化",
        "事件顺序是隐式契约，需要额外设计规避",
        "策略抽象必须靠契约测试守住，否则退化为三份不同语义",
    ]:
        write(tf, item, 12.5, INK, bullet=True, space_before=10)
    tf = textbox(s, Emu(700000), Emu(5750000), Emu(10800000), Emu(600000), 13, INK, True)
    write(tf, "一句话总结：设计模式的价值不在类图好看，而在“下一次变更要改几行”。", 13, INK, True)
    page_no(s, 14, total)

    # 15 结束
    s = blank(prs)
    bg = s.shapes.add_shape(1, Emu(0), Emu(0), W, H)
    bg.fill.solid()
    bg.fill.fore_color.rgb = INK
    bg.line.fill.background()
    tf = textbox(s, Emu(0), Emu(2600000), W, Emu(900000), 40, WHITE, True, align=PP_ALIGN.CENTER)
    write(tf, "谢谢，请提问", 40, WHITE, True)
    tf = textbox(s, Emu(0), Emu(3600000), W, Emu(600000), 14, RGBColor(0xA9, 0xBC, 0xDE), align=PP_ALIGN.CENTER)
    write(tf, "代码仓库 ______________　　公网地址 ______________", 14, RGBColor(0xA9, 0xBC, 0xDE))
    tf = textbox(s, Emu(0), Emu(4200000), W, Emu(500000), 12, RGBColor(0x7E, 0x92, 0xB8), align=PP_ALIGN.CENTER)
    write(tf, "两个标签：baseline-v1 / change-v2　|　30 项测试全通过　|　文档见 docs/", 12,
          RGBColor(0x7E, 0x92, 0xB8))

    prs.save(OUT)
    print(f"OK {OUT} ({OUT.stat().st_size} bytes, {len(prs.slides.__iter__.__self__._sldIdLst)} slides)")


if __name__ == "__main__":
    build()
