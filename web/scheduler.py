from apscheduler.schedulers.background import BackgroundScheduler
from web.config_mgr import config_mgr
from web.engine_runner import engine_runner, log_buffer


class TaskScheduler:
    def __init__(self):
        self._scheduler = BackgroundScheduler()
        self._job_id = "freesub_periodic_update"

    def start(self):
        if not self._scheduler.running:
            self._scheduler.start()
            self.reschedule()
            log_buffer.write("[*] 定时任务调度器已启动")

    def shutdown(self):
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def reschedule(self):
        cfg = config_mgr.get_config().get("scheduler", {})
        enabled = cfg.get("enabled", True)
        hours = max(1, int(cfg.get("interval_hours", 6)))

        if self._scheduler.get_job(self._job_id):
            self._scheduler.remove_job(self._job_id)

        if enabled:
            self._scheduler.add_job(
                self._trigger_job,
                "interval",
                hours=hours,
                id=self._job_id,
                name="FreeSub 定时节点更新"
            )
            log_buffer.write(f"[*] 定时任务已配置: 每 {hours} 小时自动执行一次")
        else:
            log_buffer.write("[*] 定时任务已暂停")

    def _trigger_job(self):
        log_buffer.write("[*] ⏰ 触发定时自动测活任务...")
        engine_runner.run_pipeline_async()


scheduler = TaskScheduler()
