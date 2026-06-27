"""消息适配器 — MQ消息 / DB记录 → TaskConfig 对象"""
import json
from schemas.task_schema import TaskConfig


def message_to_task_config(message: dict) -> TaskConfig:
    """
    将 MQ 消息或 task_queue 记录转为 TaskConfig

    支持两种格式:
      1. 标准化JSON格式 (文档中的控制台参数示例)
      2. task_queue.task_params 格式
    """
    # 格式1: 标准化格式
    if "taskId" in message or "scriptCode" in message:
        return TaskConfig.from_json(message)

    # 格式2: task_queue 记录格式
    task_uuid = message.get("task_uuid", "")
    params_str = message.get("task_params", "")
    params = {}
    if params_str:
        try:
            params = json.loads(params_str) if isinstance(params_str, str) else params_str
        except:
            pass

    return TaskConfig(
        task_id=task_uuid,
        trace_id=params.get("trace_id", task_uuid),
        script_code=message.get("script_name", params.get("script_name", "")),
        account=params.get("shop_name", params.get("account", "")),
        start_date=params.get("business_date", params.get("start_date", "")),
        collection_type=params.get("collect_type", params.get("collection_type", "Daily")),
        shops=params.get("shops", [params.get("shop_name", "")]) if params else [],
        countries=params.get("countries", []),
    )


def task_config_to_message(config: TaskConfig) -> dict:
    """将 TaskConfig 序列化为消息"""
    return {
        "taskId": config.task_id,
        "traceId": config.trace_id,
        "scriptCode": config.script_code,
        "collectorType": config.collector_type,
        "machineCode": config.machine_code,
        "timeoutSec": config.timeout_sec,
        "priority": config.priority,
        "params": {
            "account": config.account,
            "countries": config.countries,
            "shops": config.shops,
            "startDate": config.start_date,
            "endDate": config.end_date,
            "recollect": config.recollect,
            "collectionType": config.collection_type,
            "excludeCountry": config.exclude_country,
        },
        "callback": config.callback,
    }
