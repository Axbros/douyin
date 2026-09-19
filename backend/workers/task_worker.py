"""抖音任务执行 Worker：进入直播间并按审核话术发送评论。"""
import asyncio
import os
import random
import re
import sys
from datetime import datetime

from playwright.async_api import async_playwright
from sqlalchemy import func, select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.crypto import decrypt_storage_state
from app.core.proxy_pool import browser_proxy_for_account
from app.core.proxy_tunnel import Socks5Bridge
from app.core.browser_preview import answer_screenshot_requests
from app.core.browser_resources import remove_resource, resource_heartbeat
from app.core.database import SessionLocal, redis_client
from app.core.worker_registry import heartbeat_worker, mark_worker_offline, register_worker
from app.models import AccountLog, CommentLog, DouyinAccount, Script, SensitiveWord, Task, TaskAccount, TaskScript
from src.sender import CommentSender

WORKER_HEARTBEAT_KEY = "douyin:task-worker:heartbeat"
WORKER_HEARTBEAT_TTL_SECONDS = 300


class LoginStateExpired(RuntimeError):
    pass


async def heartbeat(worker_id: int):
    while True:
        try:
            await redis_client.set(WORKER_HEARTBEAT_KEY, datetime.now().isoformat(), ex=WORKER_HEARTBEAT_TTL_SECONDS)
            await heartbeat_worker(worker_id)
        except Exception:
            pass
        await asyncio.sleep(5)


async def wait_for_assignment_stop(assignment_id: int, seconds: float, page=None) -> bool:
    """等待评论间隔，同时让移除账号/停止任务最多 2 秒内生效。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    while loop.time() < deadline:
        if page:
            await answer_screenshot_requests("task", assignment_id, page)
        if await redis_client.lpop(f"douyin:task-account:stop:{assignment_id}"):
            return True
        await asyncio.sleep(min(1, max(0, deadline - loop.time())))
    return bool(await redis_client.lpop(f"douyin:task-account:stop:{assignment_id}"))


def find_sensitive_word(content: str, words):
    for item in words:
        try:
            if item.match_type == "exact" and content == item.word:
                return item.word
            if item.match_type == "contains" and item.word in content:
                return item.word
            if item.match_type == "regex" and re.search(item.word, content):
                return item.word
        except re.error:
            print(f"[TaskWorker] 忽略无效敏感词正则: {item.word}", flush=True)
    return None
from src.platforms import create_platform


async def assign_replacement_account(task_id: int, failed_account_id: int) -> int | None:
    """为仍在执行的任务补充一个同来源账号；没有可用账号时保持现状。"""
    async with SessionLocal() as db:
        task = await db.scalar(select(Task).where(
            Task.id == task_id,
            Task.status.in_(("running", "paused")),
            Task.deleted_at.is_(None),
        ).with_for_update())
        if not task:
            return None

        conditions = [
            DouyinAccount.id != failed_account_id,
            DouyinAccount.enabled.is_(True),
            DouyinAccount.status == "available",
            DouyinAccount.current_task_id.is_(None),
            DouyinAccount.encrypted_storage_state.is_not(None),
            DouyinAccount.deleted_at.is_(None),
        ]
        if task.account_source == "customer":
            conditions.extend((
                DouyinAccount.ownership_type == "customer",
                DouyinAccount.owner_customer_id == task.customer_id,
            ))
        else:
            conditions.append(DouyinAccount.ownership_type == "platform")
        replacement = await db.scalar(select(DouyinAccount).where(
            *conditions,
        ).order_by(func.rand()).limit(1).with_for_update())
        if not replacement:
            print(f"[TaskWorker] 任务 {task_id} 暂无可用替补账号", flush=True)
            return None

        assignment = await db.scalar(select(TaskAccount).where(
            TaskAccount.task_id == task_id,
            TaskAccount.account_id == replacement.id,
        ).with_for_update())
        if assignment:
            assignment.status = "assigned"
            assignment.assigned_by = None
            assignment.assigned_at = datetime.now()
            assignment.removed_at = None
            assignment.last_error = None
            assignment.deleted_at = None
        else:
            assignment = TaskAccount(task_id=task_id, account_id=replacement.id, status="assigned")
            db.add(assignment)
        replacement.status = "busy"
        replacement.current_task_id = task_id
        replacement.last_error = None
        db.add(AccountLog(
            account_id=replacement.id,
            event_type="replacement_assigned",
            detail={"task_id": task_id, "replaced_account_id": failed_account_id},
        ))
        await db.commit()
        await db.refresh(assignment)

    await redis_client.delete(f"douyin:task-account:stop:{assignment.id}")
    await redis_client.rpush("douyin:task-accounts", str(assignment.id))
    print(
        f"[TaskWorker] 任务 {task_id} 已使用账号 {replacement.id} 替补异常账号 {failed_account_id}",
        flush=True,
    )
    return replacement.id


async def run_account(task_id: int, assignment_id: int, account_id: int, live_url: str, worker_id: int):
    platform = create_platform("douyin")
    playwright = browser = context = None
    proxy_bridge = None
    resource_task = None
    failed = False
    login_expired = False
    claimed = False
    needs_replacement = False
    try:
        async with SessionLocal() as db:
            account = await db.get(DouyinAccount, account_id)
            assignment = await db.scalar(select(TaskAccount).where(TaskAccount.id == assignment_id).with_for_update())
            if not account or not assignment or assignment.status != "assigned" or not account.encrypted_storage_state:
                return
            assignment.status = "running"
            account.current_worker_id = worker_id
            await db.commit()
            claimed = True
            state = decrypt_storage_state(account.encrypted_storage_state)
            proxy_config = await browser_proxy_for_account(db, account)
        if proxy_config:
            proxy_bridge = Socks5Bridge(**proxy_config)
            browser_proxy = await proxy_bridge.start()
        else:
            browser_proxy = None
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true",
            proxy=browser_proxy,
        )
        context = await browser.new_context(storage_state=state)
        page = await context.new_page()
        resource_task = asyncio.create_task(resource_heartbeat("task", assignment_id, page, account_id=account_id, task_id=task_id))
        await page.goto(live_url, wait_until="domcontentloaded", timeout=30000)
        if not await platform.check_logged_in(page, context):
            raise LoginStateExpired("登录状态已失效，请重新扫码登录")
        async with SessionLocal() as db:
            db.add(AccountLog(account_id=account_id, event_type="task_browser_started", detail={"task_id": task_id, "live_url": live_url}))
            await db.commit()
        print(f"[TaskWorker] 账号 {account_id} 已打开直播链接 {live_url}，任务 {task_id}", flush=True)
        async with SessionLocal() as db:
            scripts = list(await db.scalars(select(Script).join(
                TaskScript, TaskScript.script_id == Script.id
            ).where(
                TaskScript.task_id == task_id, Script.status == "approved",
                Script.deleted_at.is_(None), TaskScript.deleted_at.is_(None),
            ).order_by(TaskScript.sort_order.asc(), TaskScript.id.asc())))
            sensitive_words = list(await db.scalars(select(SensitiveWord).where(
                SensitiveWord.enabled.is_(True), SensitiveWord.deleted_at.is_(None)
            )))
        sender = CommentSender(page, {
            "min_interval": 1,
            "max_interval": 1,
            "max_length": 500,
        }, platform=platform)
        while True:
            await answer_screenshot_requests("task", assignment_id, page)
            if not browser.is_connected() or page.is_closed():
                raise RuntimeError("任务浏览器窗口已关闭")
            async with SessionLocal() as db:
                task = await db.get(Task, task_id)
                if not task or task.status in {"stopped", "failed", "completed"}:
                    break
                task_status = task.status
                min_interval, max_interval = task.min_interval_seconds, task.max_interval_seconds
                account_row = await db.get(DouyinAccount, account_id)
                if account_row:
                    account_row.last_heartbeat_at = datetime.now()
                    account_row.status = "paused" if task_status == "paused" else "busy"
                    await db.commit()
            if task_status == "paused" or not scripts:
                if await redis_client.lpop(f"douyin:task-account:stop:{assignment_id}"):
                    break
                await asyncio.sleep(2)
                continue
            interrupted = await wait_for_assignment_stop(
                assignment_id, random.uniform(min_interval, max_interval), page
            )
            if interrupted:
                break
            # 休眠期间可能被暂停、停止或由管理员移除，发送前必须再次确认。
            async with SessionLocal() as db:
                task = await db.get(Task, task_id)
                assignment = await db.get(TaskAccount, assignment_id)
                if not task or task.status in {"stopped", "failed", "completed"}:
                    break
                if not assignment or assignment.status in {"removed", "completed", "error"}:
                    break
                if task.status == "paused":
                    continue
            if task.script_order_mode == "sequential":
                sequence = await redis_client.incr(f"douyin:task:script-sequence:{task_id}")
                script = scripts[(sequence - 1) % len(scripts)]
            else:
                script = random.choices(scripts, weights=[max(1, s.weight) for s in scripts], k=1)[0]
            matched_word = find_sensitive_word(script.content, sensitive_words)
            if matched_word:
                async with SessionLocal() as db:
                    db.add(CommentLog(
                        task_id=task_id, account_id=account_id, live_url=live_url,
                        content=script.content, result="blocked_sensitive", sensitive_word=matched_word,
                        failure_reason="评论包含敏感内容，已被系统拦截",
                    ))
                    await db.commit()
                print(f"[TaskWorker] 账号 {account_id} 命中敏感词，跳过评论: {matched_word}", flush=True)
                continue
            ok = await sender.send_comment(script.content)
            async with SessionLocal() as db:
                db.add(CommentLog(
                    task_id=task_id, account_id=account_id, live_url=live_url,
                    content=script.content, result="sent" if ok else "failed",
                    failure_reason=None if ok else "页面操作未确认评论发送成功",
                    sent_at=datetime.now(),
                ))
                if not ok:
                    failed = True
                    needs_replacement = True
                    failure_reason = "页面操作未确认评论发送成功"
                    assignment = await db.get(TaskAccount, assignment_id)
                    if assignment:
                        assignment.status = "error"
                        assignment.last_error = failure_reason
                    account_row = await db.get(DouyinAccount, account_id)
                    if account_row:
                        account_row.status = "error"
                        account_row.last_error = failure_reason
                    db.add(AccountLog(
                        account_id=account_id,
                        event_type="comment_failed",
                        detail={"task_id": task_id, "live_url": live_url, "content": script.content, "reason": failure_reason},
                    ))
                await db.commit()
            print(f"[TaskWorker] 账号 {account_id} 评论{'成功' if ok else '失败'}: {script.content}", flush=True)
            if not ok:
                break
    except Exception as exc:
        failed = True
        needs_replacement = True
        login_expired = isinstance(exc, LoginStateExpired)
        print(f"[TaskWorker] 账号 {account_id} 执行异常: {type(exc).__name__}: {exc}", flush=True)
        async with SessionLocal() as db:
            assignment = await db.get(TaskAccount, assignment_id)
            if assignment:
                assignment.status = "error"
                assignment.last_error = f"{type(exc).__name__}: {exc}"[:1000]
            account = await db.get(DouyinAccount, account_id)
            if account:
                account.last_error = f"{type(exc).__name__}: {exc}"[:1000]
                account.status = "unlogged" if login_expired else "error"
                if login_expired:
                    account.encrypted_storage_state = None
                db.add(AccountLog(account_id=account_id, event_type="login_expired" if login_expired else "task_error", detail={"task_id": task_id, "reason": account.last_error}))
            await db.commit()
    finally:
        if resource_task:
            resource_task.cancel()
            await asyncio.gather(resource_task, return_exceptions=True)
            try:
                await remove_resource("task", assignment_id)
            except Exception:
                pass
        if context:
            try:
                await context.close()
            except Exception:
                pass
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        if playwright:
            try:
                await playwright.stop()
            except Exception:
                pass
        if proxy_bridge:
            await proxy_bridge.close()
        if claimed:
            async with SessionLocal() as db:
                assignment = await db.get(TaskAccount, assignment_id)
                if assignment and assignment.status == "running":
                    assignment.status = "completed"
                account = await db.get(DouyinAccount, account_id)
                if account and account.current_task_id == task_id:
                    account.current_task_id = None
                    account.current_worker_id = None
                    if not failed:
                        account.status = "available" if account.enabled else "disabled"
                    db.add(AccountLog(account_id=account_id, event_type="task_browser_stopped", detail={"task_id": task_id, "failed": failed}))
                await db.commit()
        if needs_replacement:
            try:
                await assign_replacement_account(task_id, account_id)
            except Exception as exc:
                print(f"[TaskWorker] 任务 {task_id} 分配替补账号失败: {type(exc).__name__}: {exc}", flush=True)


async def run_task(task_id: int, worker_id: int):
    async with SessionLocal() as db:
        task = await db.get(Task, task_id)
        if not task or task.status != "pending":
            return
        assignments = list(await db.scalars(select(TaskAccount).where(
            TaskAccount.task_id == task_id,
            TaskAccount.status == "assigned",
            TaskAccount.deleted_at.is_(None),
        )))
        task.status = "running"
        task.started_at = datetime.now()
        await db.commit()
    await asyncio.gather(*(
        run_account(task_id, a.id, a.account_id, task.live_url, worker_id) for a in assignments
    ))
    async with SessionLocal() as db:
        task = await db.get(Task, task_id)
        if task and task.status in {"running", "paused"}:
            active_count = await db.scalar(select(TaskAccount.id).where(
                TaskAccount.task_id == task_id,
                TaskAccount.status.in_(("assigned", "running")),
                TaskAccount.deleted_at.is_(None),
            ).limit(1))
            error_count = await db.scalar(select(TaskAccount.id).where(
                TaskAccount.task_id == task_id,
                TaskAccount.status == "error",
                TaskAccount.deleted_at.is_(None),
            ).limit(1))
            if not active_count and error_count:
                task.status = "failed"
                task.failure_reason = "所有执行账号均已异常停止"
                await db.commit()


async def run_added_assignment(assignment_id: int, worker_id: int):
    async with SessionLocal() as db:
        assignment = await db.get(TaskAccount, assignment_id)
        if not assignment or assignment.status != "assigned":
            return
        task = await db.get(Task, assignment.task_id)
        if not task or task.status not in {"running", "paused"}:
            return
        arguments = (task.id, assignment.id, assignment.account_id, task.live_url)
    await run_account(*arguments, worker_id)


async def main():
    print("[TaskWorker] 已启动，等待任务...", flush=True)
    await redis_client.ping()
    worker_id, worker_key = await register_worker("task")
    print(f"[TaskWorker] 已注册实例: {worker_key}", flush=True)
    heartbeat_task = asyncio.create_task(heartbeat(worker_id))
    running_jobs: set[asyncio.Task] = set()
    def job_finished(job: asyncio.Task):
        running_jobs.discard(job)
        if job.cancelled():
            return
        error = job.exception()
        if error:
            print(f"[TaskWorker] 后台任务异常: {type(error).__name__}: {error}", flush=True)
    try:
        while True:
            item = await redis_client.blpop(["douyin:tasks", "douyin:task-accounts"], timeout=5)
            if item:
                queue_name = item[0].decode() if isinstance(item[0], bytes) else item[0]
                item_id = int(item[1])
                coroutine = run_task(item_id, worker_id) if queue_name == "douyin:tasks" else run_added_assignment(item_id, worker_id)
                job = asyncio.create_task(coroutine)
                running_jobs.add(job)
                job.add_done_callback(job_finished)
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
        for job in running_jobs:
            job.cancel()
        await asyncio.gather(*running_jobs, return_exceptions=True)
        await redis_client.delete(WORKER_HEARTBEAT_KEY)
        await mark_worker_offline(worker_id)


if __name__ == "__main__":
    asyncio.run(main())
