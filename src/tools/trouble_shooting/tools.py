import json
from typing import Optional

import requests
from agents import function_tool
from src.utils import JsonUtils

@function_tool(name_override="finish")
def finish(conclusion: str) -> str:
    """
    停止任务，同时使用当前工具输出最终的分析结论

    Args:
        conclusion: 分析结论
    """
    return "the conclusion is: " + conclusion

@function_tool
def analysis_jank_event(
    end_time: Optional[str] = None,
    start_time: Optional[str] = None,
    vin: Optional[str] = None,
    jank_event: Optional[str] = None,
    only_analysis: bool = True,
    top_pkg_num: int = 1
):
    """
    向性能稳定性服务发送请求分析卡顿数据，如果only_analysis为True，返回数据包括卡顿次数最多的应用、该应用卡顿频发的时间、卡顿各阶段耗时最严重的两个耗时字段
    
    Args:
        end_time: 结束时间，格式为'YYYY-MM-DD HH:MM:SS'
        start_time: 开始时间，格式为'YYYY-MM-DD HH:MM:SS'
        vin: 车辆识别码，用于标识特定车辆
        jank_event: 卡顿事件类型，例如'SimpleJank'
        only_analysis: 是否仅分析数据而不获取原始数据，默认为True
        top_pkg_num: 返回的顶部包数量，用于限制分析结果中的包数量，默认为1
    """
    url = "https://performance-stability-service.fc.chj.cloud/api/v1/vehicle-data/gfx"
    
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json"
    }
    
    # 准备请求数据
    payload = {
        "end_time": end_time,
        "start_time": start_time,
        "vin": vin,
        "jank_event": jank_event,
        "only_analysis": only_analysis,
        "top_pkg_num": top_pkg_num
    }
    
    # 移除None值，避免发送不必要的参数
    payload = {k: v for k, v in payload.items() if v is not None}
    
    # 发送POST请求
    response = requests.post(url, headers=headers, json=payload)
    
    # 返回响应体字符串
    return f"Tool: analysis_jank_event\nParameters: {json.dumps(payload, indent=2)}\nResponse: \n{JsonUtils.format_json(response.text)}"


@function_tool
def fetch_vehicle_event(
    end_time: Optional[str] = None,
    start_time: Optional[str] = None,
    vin: Optional[str] = None,
    problem_type: Optional[str] = None,
    page_no: int = 1,
    page_size: int = 10
):
    """
    向性能稳定性服务发送请求获取车辆事件数据,响应数据中核心字段包括包括json_value字符串，message字符串

    message是log的原始格式
    binder耗时
    log格式： binder_sample(descriptor|3),(method_num|1|5),(time|1|3),(blocking_package|3),(sample_percent|1|6)
    log sample binder_sample: [android.os.IServiceManager,2,5,com.android.phone,1]
    android.os.IServiceManager    binder通信aidl描述符
    2    binder通信方法序号
    5    binder通信耗时
    com.android.phone    打印该log的进程名
    1    binder采集日志中time与阈值的百分比

    looper耗时
    looper_sample(process_name|3),(msg_target|3),(msg_what|1|6),(msg_callback|3),(wait_time|1|6),(run_time|1|6),(procState|1|6),(schedule|duration|1|6),(utm_duration|3),(io_wait_duration|3),(sched_runnable_time|3),(stm_duration|3),(major_fault|3)
    log sample looper_sample: [com.liauto.onemap,android.os.Handler,0,null,479,43,2,0,0,0,0,0]
    进程：    com.liauto.onemap
    handler:    android.os.Handler
    msg:    0
    msg_callback:    null
    wait_time:    479 在messagequeue中等待时长，单位ms
    run_time:    43   当前msg执行时长，单位ms
    procState:    2   当前进程状态
    schedule_duration:    0   在messagequeue中减去上一msg时长后的等待执行时长
    utm_duration:    0    代码在cpu上真正耗时时长，单位是ms，10进位，小于10都是0
    io_wait_duration:    0   当前msg在执行时等待io的时长
    sched_runnable_time:    0  等待调度时长
    stm_duration:    0   stime内核模式下话费的时间
    major_fault:    0    该任务访问内存需要从硬盘拷数据而发生的缺页（主缺页）
    

    
    Args:
        end_time: 结束时间，格式为'YYYY-MM-DD HH:MM:SS'
        start_time: 开始时间，格式为'YYYY-MM-DD HH:MM:SS'
        vin: 车辆识别码，用于标识特定车辆
        problem_type: 问题类型，包括:'looper_sample'、"binder_sample"
        page_no: 页码，默认为1
        page_size: 每页数据量，默认为10
    """
    url = "https://performance-stability-service.fc.chj.cloud/api/v1/vehicle-data/event"
    
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json"
    }
    
    # 准备请求数据
    payload = {
        "end_time": end_time,
        "start_time": start_time,
        "vin": vin,
        "problem_type": problem_type,
        "page_no": page_no,
        "page_size": page_size
    }
    
    # 移除None值，避免发送不必要的参数
    payload = {k: v for k, v in payload.items() if v is not None}
    
    # 发送POST请求
    response = requests.post(url, headers=headers, json=payload)
    
    # 返回响应体字符串
    return f"Tool: fetch_vehicle_event\nParameters: {json.dumps(payload, indent=2)}\nResponse: \n{JsonUtils.format_json(response.text)}"
