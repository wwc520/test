import requests
import time
import schedule
from datetime import datetime

# 配置常量
API_URL = 'https://m.hsyuntai.com/med/hp/hospitals/100044/registration/doctorDetails225'
HEADERS = {
    'Host': 'm.hsyuntai.com',
    'unicode': 'ZwiT3izIT9OmC4ggggytpe60D3t3PD',
    # ...其他headers内容...
}
PARAMS = {
    'branchId': '',
    'docId': '489437',
    'filtrate': 'Y',
    'isShowTime': 'false',
    'outpatientId': '',
    'schListType': 'true',
    'type': '0'
}


def log(message, level="INFO"):
    """带时间戳的日志记录"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] [{level}] {message}")


def fetch_data():
    """发送请求并返回处理后的JSON数据"""
    try:
        response = requests.get(API_URL, headers=HEADERS, params=PARAMS, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        log(f"请求失败: {str(e)}", "ERROR")
    except ValueError as e:
        log(f"JSON解析失败: {str(e)}", "ERROR")
    return None


def process_schedules(data):
    """处理排班数据并返回有效号源"""
    available_slots = []
    if not isinstance(data, list):
        log("响应数据结构异常", "WARNING")
        return available_slots

    for item in data:
        if not isinstance(item.get('data'), list) or not item.get('result'):
            continue

        try:
            now_time = datetime.strptime(item['nowTime'], "%Y-%m-%d %H:%M:%S")
            current_year = now_time.year
            cutoff_date = datetime(current_year, 3, 6).date()  # 截止日期设置
        except (KeyError, ValueError) as e:
            log(f"时间解析失败：{str(e)}", "WARNING")
            continue

        for schedule_item in item['data']:
            if not isinstance(schedule_item, dict):
                continue

            state = schedule_item.get('stateShown', '')
            cost = schedule_item.get('cost')
            sch_date_str = schedule_item.get('schDate')

            if any([
                '号满' in state,
                cost != 17,  # 费用过滤
                not sch_date_str
            ]):
                continue

            try:
                sch_date = datetime.strptime(
                    f"{current_year}-{sch_date_str}", "%Y-%m-%d"
                ).date()
                if sch_date >= cutoff_date:
                    continue
            except ValueError as e:
                log(f"日期格式错误：{sch_date_str}，错误：{str(e)}", "WARNING")
                continue

            available_slots.append({
                '科室': schedule_item.get('deptName', '未知科室'),
                '日期': f"{current_year}-{sch_date_str}",
                '时段': f"{schedule_item.get('startTime', '')}-{schedule_item.get('endTime', '')}",
                '号源状态': state,
                '剩余号数': schedule_item.get('remainNo', 0),
                '诊室地址': schedule_item.get('clinicAddr', '地址未知')
            })

    return available_slots


def format_notification(slots):
    """格式化通知内容"""
    html_content = """
    <h3>🏥 发现可用号源 ({count}个)</h3>
    <table border="1" cellpadding="5">
        <tr>
            <th>科室</th>
            <th>日期</th>
            <th>时段</th>
            <th>状态</th>
            <th>剩余号数</th>
            <th>诊室</th>
        </tr>
        {rows}
    </table>
    """
    rows = []
    for slot in slots:
        rows.append(f"""
        <tr>
            <td>{slot['科室']}</td>
            <td>{slot['日期']}</td>
            <td>{slot['时段']}</td>
            <td>{slot['号源状态']}</td>
            <td>{slot['剩余号数']}</td>
            <td>{slot['诊室地址']}</td>
        </tr>
        """)
    return html_content.format(count=len(slots), rows='\n'.join(rows))


def send_wechat(msg):
    """发送微信通知"""
    token = 'caeb249141054fd7bf0ec7cb816d128e'
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    title = f'{current_time}号源监控'
    content = title + msg
    template = 'html'

    try:
        url = f"https://www.pushplus.plus/send?token={token}&title={title}&content={content}&template={template}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        log(f"微信通知发送失败: {str(e)}", "ERROR")
        return False


def check_appointments():
    """主检查逻辑"""
    log("开始检查号源...")
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M')

    log("current_time:"+current_time)
    data = fetch_data()
    if not data:
        return

    available = process_schedules(data)
    if available:
        log_msg = f"发现 {len(available)} 个可用号源！"
        log(log_msg, "SUCCESS")
        notification_content = format_notification(available)

        if send_wechat(notification_content):
            log("微信通知发送成功", "SUCCESS")
        else:
            log("微信通知发送失败", "WARNING")

        for slot in available:
            log(f"[可用号源] {slot['科室']} {slot['日期']} {slot['时段']} | {slot['号源状态']} | 诊室: {slot['诊室地址']}")
    else:
        log("当前没有符合要求的号源")


if __name__ == "__main__":
    log("号源监控已启动...")

    schedule.every(1).minutes.do(check_appointments)

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        log("监控已手动停止")