from typing import List

from pydantic import BaseModel, Field

class SubAlarmRequest(BaseModel):
    """
    告警信息子条目请求模型
    """
    alarm_rule_id: str = Field(..., description="告警规则ID")
    vin_id: str = Field(..., description="车辆VIN")
    alarm_time: str = Field(..., description="告警时间")

    class Config: 
        extra = "allow" # 允许额外字段



class AlarmRequest(BaseModel):
    """
    告警请求模型
    """
    alarm_name: str = Field(..., description="告警名称")
    alarm_description: str = Field(..., description="告警描述")
    alarm_time: str = Field(..., description="告警时间")
    sub_alarms: List[SubAlarmRequest] = Field(..., description="子告警列表")


