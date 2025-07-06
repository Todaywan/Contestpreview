import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz
import re
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
import time


import os, sys
sys.stderr = open(os.devnull, 'w')
def get_this_week_range():
    # 使用北京时间（Asia/Shanghai）为基准
    tz = pytz.timezone('Asia/Shanghai')
    now = datetime.now(tz)
    start = now.replace(second=0, microsecond=0)
    end = start + timedelta(days=7)
    # 转为UTC，便于和比赛时间（UTC）比较
    start_utc = start.astimezone(pytz.utc)
    end_utc = end.astimezone(pytz.utc)
    return start_utc, end_utc

def format_cf_time(start_time, duration):
    # 转为北京时间
    tz = pytz.timezone('Asia/Shanghai')
    start_time = start_time.astimezone(tz)
    end_time = (start_time + duration)
    return f"{start_time.month}.{start_time.day} {start_time.hour}:{start_time.minute:02d}-{end_time.month}.{end_time.day} {end_time.hour}:{end_time.minute:02d}"

def get_codeforces_contests():
    url = "https://codeforces.com/api/contest.list"
    resp = requests.get(url)
    data = resp.json()
    contests = []
    if data['status'] != 'OK':
        print("[DEBUG] Codeforces API 获取失败")
        return contests
    start, end = get_this_week_range()
    for c in data['result']:
        # 只要未来的比赛
        if c['phase'] != 'BEFORE':
            continue
        # 比赛开始时间是秒级时间戳（UTC）
        contest_time_utc = datetime.fromtimestamp(c['startTimeSeconds'], pytz.utc)
        duration = timedelta(seconds=c['durationSeconds'])
        if start <= contest_time_utc < end:
            contests.append({
                "name": c['name'],
                "start_time": contest_time_utc,
                "duration": duration,
                "link": f"https://codeforces.com/contest/{c['id']}"
            })
    return contests

def get_atcoder_contests():
    url = "https://atcoder.jp/contests/"
    resp = requests.get(url)
    soup = BeautifulSoup(resp.text, "html.parser")
    contests = []
    table = soup.find("div", {"id": "contest-table-upcoming"}).find("table")
    rows = table.find_all("tr")[1:]
    start, end = get_this_week_range()
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 3:
            continue
        time_str = cols[0].get_text(strip=True)
        name = cols[1].get_text(strip=True)
        link = "https://atcoder.jp" + cols[1].find("a")["href"]
        # 解析时间（日本时间，转为北京时间显示）
        try:
            contest_time_jst = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S%z")
            contest_time_bj = contest_time_jst - timedelta(hours=1)  # 转为北京时间
        except Exception:
            continue
        # 判断是否在未来7天（用UTC范围判断）
        contest_time_utc = contest_time_jst.astimezone(pytz.utc)
        if start <= contest_time_utc < end:
            week_day = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            time_fmt = f"{contest_time_bj.month}/{contest_time_bj.day}({week_day[contest_time_bj.weekday()]}) {contest_time_bj.hour:02d}:{contest_time_bj.minute:02d}"
            contests.append({
                "name": name,
                "time_fmt": time_fmt,
                "link": link
            })
    return contests

def get_luogu_contests():
    # 优先用 Selenium 自动抓取
    try:
        edge_path = './msedgedriver.exe'  # 确保和脚本同目录
        options = Options()
        options.add_argument('--headless')  # 恢复无头模式
        options.add_argument('--disable-gpu')
        service = EdgeService(executable_path=edge_path)
        driver = webdriver.Edge(service=service, options=options)
        driver.get('https://www.luogu.com.cn/contest/list')
        time.sleep(5)  # 等待页面加载
        last_height = driver.execute_script('return document.body.scrollHeight')
        for _ in range(5):
            driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
            time.sleep(2)
            new_height = driver.execute_script('return document.body.scrollHeight')
            if new_height == last_height:
                break
            last_height = new_height
        html = driver.page_source
        driver.quit()
        soup = BeautifulSoup(html, 'html.parser')
        contest_rows = soup.select('div.row')
        contests = []
        start, end = get_this_week_range()
        for row in contest_rows:
            # 状态
            status_tag = row.find('span', class_='status')
            status = status_tag.get_text(strip=True) if status_tag else ''
            if status != '未开始':
                continue
            # 比赛名
            name_tag = row.find('a', class_='name')
            if not name_tag:
                continue
            name = name_tag.get_text(strip=True)
            link = 'https://www.luogu.com.cn' + name_tag['href']
            # 直接提取所有 <time> 标签，分别为起止时间
            time_tags = row.find_all('time')
            print(f"[DEBUG] name={name}, time_tags={[t.get_text(strip=True) for t in time_tags]}")
            if len(time_tags) >= 2:
                start_str = time_tags[0].get_text(strip=True)
                end_str = time_tags[1].get_text(strip=True)
            else:
                print(f"[DEBUG] 跳过：time标签不足2个")
                continue
            year = datetime.now().year
            try:
                # 起始时间
                contest_time_bj = datetime.strptime(f"{year}-{start_str}", "%Y-%m-%d %H:%M")
                contest_time_bj = pytz.timezone('Asia/Shanghai').localize(contest_time_bj)
                # 结束时间：如果只有时分，补上起始年月日
                if '-' in end_str:
                    # 形如07-13 18:30，补年份
                    contest_end_bj = datetime.strptime(f"{year}-{end_str}", "%Y-%m-%d %H:%M")
                else:
                    # 形如18:30，补起始年月日（注意加空格）
                    contest_end_bj = datetime.strptime(f"{year}-{start_str[:5]} {end_str}", "%Y-%m-%d %H:%M")
                contest_end_bj = pytz.timezone('Asia/Shanghai').localize(contest_end_bj)
            except Exception as ex:
                print(f"[DEBUG] 时间解析失败: start={start_str}, end={end_str}, 错误: {ex}")
                contest_end_bj = None
            contest_time_utc = contest_time_bj.astimezone(pytz.utc)
            print(f"[DEBUG] 起始时间: {contest_time_bj}, UTC: {contest_time_utc}, 结束时间: {contest_end_bj}")
            # 只用起始时间判断是否在未来7天
            if not (start <= contest_time_utc < end):
                print(f"[DEBUG] 跳过：不在未来7天范围内")
                continue
            week_day = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            if contest_end_bj:
                time_fmt = f"{contest_time_bj.month}/{contest_time_bj.day}({week_day[contest_time_bj.weekday()]}) {contest_time_bj.hour:02d}:{contest_time_bj.minute:02d}-{contest_end_bj.hour:02d}:{contest_end_bj.minute:02d}"
            else:
                time_fmt = f"{contest_time_bj.month}/{contest_time_bj.day}({week_day[contest_time_bj.weekday()]}) {contest_time_bj.hour:02d}:{contest_time_bj.minute:02d}"
            print(f"[DEBUG] 最终加入: {name} {time_fmt}")
            contests.append({
                'name': name,
                'time_fmt': time_fmt,
                'link': link
            })
        return contests
    except Exception as e:
        url = "https://www.luogu.com.cn/api/contest/list?type=all&page=1&pageSize=100"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Cookie': '__client_id=x1945ba2c62e23b6f7186506e4ce70f3d1afe191; _uid=1475185; c3vk=a96282; CSP_TOKEN=your_csrf_token_here',
            'Referer': 'https://www.luogu.com.cn/contest/list',
            'X-CSRF-Token': 'your_csrf_token_here'
        }
        resp = requests.get(url, headers=headers)
        try:
            data = resp.json()
        except Exception as e:
            return []
        contests = []
        if data.get('code') != 200:
            return contests
        start, end = get_this_week_range()
        for c in data['data']['contests']:
            if c['status'] != 0 or c['type'] != 0:
                continue
            contest_time_bj = datetime.fromtimestamp(c['startTime'] / 1000, pytz.timezone('Asia/Shanghai'))
            contest_time_utc = contest_time_bj.astimezone(pytz.utc)
            duration = timedelta(minutes=c['duration'])
            if start <= contest_time_utc < end:
                week_day = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                end_time = contest_time_bj + duration
                time_fmt = f"{contest_time_bj.month}/{contest_time_bj.day}({week_day[contest_time_bj.weekday()]}) {contest_time_bj.hour:02d}:{contest_time_bj.minute:02d}-{end_time.hour:02d}:{end_time.minute:02d}"
                contests.append({
                    "name": c['name'],
                    "time_fmt": time_fmt,
                    "link": f"https://www.luogu.com.cn/contest/{c['id']}"
                })
        return contests

def clean_and_shorten_name(name):
    # 去除前缀特殊字符
    name = re.sub(r'^[^\w\d]+', '', name)
    # Codeforces
    name = name.replace('Codeforces', 'CF')
    # AtCoder Beginner Contest
    name = re.sub(r'AtCoder Beginner Contest', 'ABC', name)
    # AtCoder Heuristic Contest
    name = re.sub(r'AtCoder Heuristic Contest', 'AHC', name)
    return name.strip()

def main():
    with open('output.txt', 'w', encoding='utf-8') as f:
        print("本周赛事预告~\n", file=f)
        cf_contests = get_codeforces_contests()
        atcoder_contests = get_atcoder_contests()
        luogu_contests = get_luogu_contests()

        print("Codeforces:", file=f)
        if not cf_contests:
            print("本周暂无Codeforces比赛。", file=f)
        else:
            for c in cf_contests:
                name = clean_and_shorten_name(c["name"])
                time_str = format_cf_time(c["start_time"], c["duration"])
                print(f"{name}  {time_str}", file=f)

        print("\nAtcoder:", file=f)
        if not atcoder_contests:
            print("本周暂无Atcoder比赛。", file=f)
        else:
            for c in atcoder_contests:
                name = clean_and_shorten_name(c["name"])
                print(f"{name} {c['time_fmt']}", file=f)

        print("\nLuogu:", file=f)
        if not luogu_contests:
            print("本周暂无Luogu比赛。", file=f)
        else:
            for c in luogu_contests:
                # 不做特殊字符处理，直接输出原始名称
                print(f"{c['name']} {c['time_fmt']}", file=f)

if __name__ == "__main__":
    main()