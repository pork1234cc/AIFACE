# -*- coding: utf-8 -*-
"""
license_guard tkinter 便捷集成

提供授权信息展示、定期验证等 tkinter UI 辅助函数。
"""
import sys
import logging
import threading
from datetime import datetime, timedelta
import tkinter.messagebox as messagebox

from .license_client import LicenseClient

logger = logging.getLogger(__name__)


def show_license_info_tk(widget, client: LicenseClient):
    """
    弹窗展示当前授权状态。

    Args:
        widget: 任意 tkinter 组件（未使用，保持与 update_guard 一致的接口风格）
        client: LicenseClient 实例
    """
    machine_code = client.machine_code

    if not client.is_activated():
        messagebox.showinfo("授权信息", f"当前状态: 未激活\n机器码: {machine_code}")
        return

    cache = client.get_cache_info()
    expire_time = cache.get("expire_time", "")
    card_type = cache.get("card_type", "未知")
    last_verify = cache.get("last_verify", "未知")

    if expire_time == "9999-12-31 23:59:59":
        expire_display = "永久"
        remaining_text = "永久"
    elif expire_time:
        expire_display = expire_time
        try:
            exp_dt = datetime.strptime(expire_time, "%Y-%m-%d %H:%M:%S")
            remaining_text = f"{(exp_dt - datetime.now()).days} 天"
        except ValueError:
            remaining_text = "未知"
    else:
        expire_display = "未知"
        remaining_text = "未知"

    msg = (
        f"当前状态: 已激活\n"
        f"卡类型: {card_type}\n"
        f"到期时间: {expire_display}\n"
        f"剩余天数: {remaining_text}\n"
        f"上次验证: {last_verify}\n"
        f"机器码: {machine_code}"
    )
    messagebox.showinfo("授权信息", msg)


# ==================== 定期验证 ====================

# 轮询间隔：每 1 小时检查一次墙钟差
_POLL_INTERVAL_MS = 60 * 60 * 1000
# 验证阈值：墙钟差 ≥ 24 小时即触发联网验证
_VERIFY_INTERVAL = timedelta(hours=24)


def start_periodic_verify(widget, client: LicenseClient):
    """
    启动后台定期验证（wall-clock 计时模式）。

    每 1 小时轮询一次，比较 last_verify 与当前墙钟时间，差值 ≥ 24 小时
    则联网验证。系统休眠/唤醒、进程重启都能按真实墙钟时间触发，不会因
    事件循环暂停或定时器重置而漏检。

    验证失败（过期/被撤销）时弹窗提示后强制退出程序。
    永久卡（9999-12-31）同样参与定期验证。

    Args:
        widget: 任意 tkinter 组件（用于 after 定时器）
        client: LicenseClient 实例
    """
    # 永久卡也参与定期验证（v_new 安全加固）：
    # v_old 永久卡跳过验证 → 攻击者伪造永久卡凭证可终身使用，且服务端无法撤销
    # v_new 永久卡每 24h 联网验证一次 + 离线宽限被拒绝 + 服务端可下发 revoked=true

    def _verify_in_thread():
        logger.info("开始定期验证授权状态")
        ok, msg, _info = client.verify()
        widget.after(0, lambda: _handle_result(ok, msg))

    def _handle_result(ok, msg):
        if ok:
            logger.info(f"定期验证通过: {msg}")
            # verify 成功已刷新 last_verify，下一轮 1 小时后继续轮询
            widget.after(_POLL_INTERVAL_MS, _tick)
        else:
            logger.warning(f"定期验证失败: {msg}")
            messagebox.showerror("授权失败", f"授权验证失败，程序即将退出。\n\n原因：{msg}")
            sys.exit(1)

    def _tick():
        last_verify_str = client.get_cache_info().get("last_verify", "").strip()
        try:
            last_dt = datetime.strptime(last_verify_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            logger.warning("last_verify 缺失或无效，立即验证")
            threading.Thread(target=_verify_in_thread, daemon=True).start()
            return

        elapsed = datetime.now() - last_dt
        if elapsed >= _VERIFY_INTERVAL or elapsed < -timedelta(seconds=60):
            threading.Thread(target=_verify_in_thread, daemon=True).start()
        else:
            logger.debug(f"距下次 wall-clock 验证还需 {_VERIFY_INTERVAL - elapsed}")
            widget.after(_POLL_INTERVAL_MS, _tick)

    # 首次触发立即判断
    widget.after(0, _tick)
