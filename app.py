# -*- coding: utf-8 -*-
# NBA Player Report Streamlit App - Final and Stable Version (Restored Reddit & Fixed Keys)

import pandas as pd
import streamlit as st
import requests # <-- 新增：用於傳統爬蟲
from bs4 import BeautifulSoup # <-- 新增：用於 HTML 解析
import time # <-- 新增：用於設置延遲
import re # <-- 新增：用於文本處理

from nba_api.stats.static import players
from nba_api.stats.endpoints import (
    playerawards, 
    commonplayerinfo, 
    playercareerstats, 
)

# 設置 Reddit 爬蟲參數
REDDIT_BASE_URL = "https://www.reddit.com/r/nba/search/?q="
CRAWL_DELAY = 3 # <-- 設置延遲，避免被 Reddit 封鎖

# ====================================================================
# I. 數據獲取與處理的核心邏輯
# ====================================================================

@st.cache_data
def get_player_id(player_name):
    """根據球員姓名查找其唯一的 Player ID (使用 Streamlit 緩存)"""
    try:
        nba_players = players.get_players()
        player_info = [
            player for player in nba_players 
            if player['full_name'].lower() == player_name.lower()
        ]
        return player_info[0]['id'] if player_info else None
    except Exception:
        return None

def get_precise_positions(generic_position):
    """將 NBA API 返回的通用位置轉換為所有精確位置。"""
    position_map = {
        'Guard': ['PG', 'SG'], 'Forward': ['SF', 'PF'], 'Center': ['C'],
        'G-F': ['PG', 'SG', 'SF'], 'F-G': ['SG', 'SF', 'PF'], 'F-C': ['SF', 'PF', 'C'],
        'C-F': ['PF', 'C', 'SF'], 'G': ['PG', 'SG'], 'F': ['SF', 'PF'], 'C': ['C'],
    }
    positions = position_map.get(generic_position)
    if positions:
        return ", ".join(positions)
    return generic_position

def analyze_style(stats, position):
    """根據場均數據和位置，生成簡單的球員風格分析。（用於報告顯示）"""
    try:
        pts = float(stats.get('pts', 0))
        ast = float(stats.get('ast', 0))
        reb = float(stats.get('reb', 0))
    except ValueError:
        return {'core_style': '數據不足，無法分析', 'simple_rating': '請嘗試查詢有數據的賽季。'}

    HIGH_PTS, HIGH_AST, HIGH_REB = 25, 8, 10
    core_style, simple_rating = "角色球員", "可靠的輪換球員。"
    
    if pts >= HIGH_PTS and ast >= 6 and reb >= 6:
        core_style = "🌟 頂級全能巨星 (Elite All-Around Star)"
        simple_rating = "集得分、組織和籃板於一身的劃時代球員。"
    elif pts >= HIGH_PTS:
        core_style = "得分機器 (Volume Scorer)"
        simple_rating = "聯盟頂級的得分手，能夠在任何位置取分。"
    elif ast >= HIGH_AST and pts >= 15:
        core_style = "🎯 組織大師 (Playmaking Maestro)"
        simple_rating = "以傳球優先的組織核心，同時具備可靠的得分能力。"
    elif reb >= HIGH_REB and pts < 15:
        core_style = "🧱 籃板/防守支柱 (Rebounding/Defense Anchor)"
        simple_rating = "內線防守和籃板的專家，隊伍的堅實後盾。"
    else:
        core_style = "角色球員 (Role Player)"
        simple_rating = "一名可靠的輪換球員。"

    return {'core_style': core_style, 'simple_rating': simple_rating}

# ======================================
# II. 新增：Reddit 傳統爬蟲函數
# ======================================

@st.cache_data(ttl=3600 * 3) # 限制每 3 小時爬取一次，避免頻繁請求
def get_reddit_data(player_name):
    """執行 Reddit 爬蟲，獲取熱度和爭議點。"""
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.88 Safari/537.36'}
    search_query = requests.utils.quote(player_name)
    url = f"{REDDIT_BASE_URL}{search_query}&sort=new&t=week"

    time.sleep(CRAWL_DELAY) 

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return {'hot_index': '爬蟲失敗', 'top_tags': '無法連接 Reddit 數據源'}

        soup = BeautifulSoup(response.content, 'html.parser')
        
        posts = soup.find_all('div', {'class': 'Post'})
        total_posts = len(posts)
        
        tag_counts = {}
        for post in posts[:10]:
            title = post.find('h3').text if post.find('h3') else ''
            
            if 'trade' in title.lower() or '交易' in title.lower():
                tag_counts['Trade Rumor'] = tag_counts.get('Trade Rumor', 0) + 1
            if 'mvp' in title.lower():
                tag_counts['MVP Candidate'] = tag_counts.get('MVP Candidate', 0) + 1
            if 'defense' in title.lower() or '防守' in title.lower():
                tag_counts['Defensive Anchor'] = tag_counts.get('Defensive Anchor', 0) + 1
        
        top_tags = [tag for tag, count in sorted(tag_counts.items(), key=lambda item: item[1], reverse=True)]
        
        return {
            'hot_index': f"過去一週帖子數量：{total_posts}",
            'top_tags': ", ".join(top_tags) if top_tags else '無主要爭議點'
        }

    except Exception as e:
        return {'hot_index': '爬蟲發生錯誤', 'top_tags': f'數據獲取失敗: {type(e).__name__}'}


# ======================================
# III. 主數據獲取函數 (整合爬蟲)
# ======================================

def get_player_report(player_name, season='2023-24'):
    """獲取並整理特定球員的狀態報告數據。"""
    player_id = get_player_id(player_name)
    if not player_id:
        # vvvvvv 修正：確保返回的字典包含所有鍵 vvvvvv
        return {
            'error': f"找不到球員：{player_name}。請檢查姓名是否正確。",
            'team_abbr': 'N/A', 'team_full': 'N/A', 'precise_positions': 'N/A', 
            'games_played': 0, 'pts': 'N/A', 'reb': 'N/A', 'ast': 'N/A', 'stl': 'N/A', 'blk': 'N/A', 
            'tov': 'N/A', 'ato_ratio': 'N/A', 'fg_pct': 'N/A', 'ft_pct': 'N/A', 'fta_per_game': 'N/A', 
            'min_per_game': 'N/A', 'trend_analysis': {'trend_status': 'N/A', 'delta_pts': 'N/A', 'delta_reb': 'N/A', 'delta_ast': 'N/A'},
            'reddit_hot_index': 'N/A', 'reddit_top_tags': 'N/A', 'awards': [], 'season': season
        }
        # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

    try:
        # 1. 獲取官方統計數據 (NBA API)
        info = commonplayerinfo.CommonPlayerInfo(player_id=player_id)
        info_df = info.get_data_frames()[0]
        stats = playercareerstats.PlayerCareerStats(player_id=player_id)
        stats_data = stats.get_data_frames()[0]
        career_totals_df = stats.get_data_frames()[1] 
        season_stats = stats_data[stats_data['SEASON_ID'] == season]
        awards = playerawards.PlayerAwards(player_id=player_id)
        awards_df = awards.get_data_frames()[0]
        
        # 2. 獲取社群數據 (Reddit 爬蟲)
        reddit_info = get_reddit_data(player_name)
        
        report = {}
        # --- 基本資訊 ---
        generic_pos = info_df.loc[0, 'POSITION']
        report['name'] = info_df.loc[0, 'DISPLAY_FIRST_LAST']
        
        # 處理球隊邏輯
        if not season_stats.empty:
            team_abbr_list = season_stats['TEAM_ABBREVIATION'].tolist()
            if 'TOT' in team_abbr_list:
                abbrs = [a for a in team_abbr_list if a != 'TOT']
                report['team_abbr'] = ", ".join(abbrs)
                report['team_full'] = f"效力多隊: {report['team_abbr']}"
            else:
                report['team_abbr'] = team_abbr_list[0]
                report['team_full'] = team_abbr_list[0]
        else:
            report['team_abbr'] = info_df.loc[0, 'TEAM_ABBREVIATION']
            report['team_full'] = info_df.loc[0, 'TEAM_NAME'] 
        
        report['position'] = generic_pos  
        report['precise_positions'] = get_precise_positions(generic_pos) 
        
        # --- 場均數據計算 ---
        if not season_stats.empty and season_stats.iloc[-1]['GP'] > 0:
            avg_stats = season_stats.iloc[-1]
            total_gp = avg_stats['GP']
            
            # 統計數據計算
            report['games_played'] = int(total_gp) 
            report['pts'] = round(avg_stats['PTS'] / total_gp, 1) 
            report['reb'] = round(avg_stats['REB'] / total_gp, 1)
            report['ast'] = round(avg_stats['AST'] / total_gp, 1) 
            report['stl'] = round(avg_stats['STL'] / total_gp, 1) 
            report['blk'] = round(avg_stats['BLK'] / total_gp, 1) 
            report['tov'] = round(avg_stats['TOV'] / total_gp, 1)
            
            # 命中率與罰球
            report['fg_pct'] = round(avg_stats['FG_PCT'] * 100, 1) 
            report['ft_pct'] = round(avg_stats['FT_PCT'] * 100, 1)
            report['fta_per_game'] = round(avg_stats['FTA'] / total_gp, 1)
            report['min_per_game'] = round(avg_stats['MIN'] / total_gp, 1) 
            
            # 助攻失誤比 (A/TO)
            try:
                report['ato_ratio'] = round(report['ast'] / report['tov'], 2)
            except ZeroDivisionError:
                report['ato_ratio'] = 'N/A'
            
            # 生涯趨勢分析邏輯
            if not career_totals_df.empty:
                # ... (Delta 計算邏輯已在前面提供，這裡保持簡化)
                career_avg = {}
                total_gp_career = career_totals_df.loc[0, 'GP']
                career_avg['pts'] = round(career_totals_df.loc[0, 'PTS'] / total_gp_career, 1)
                delta_pts = report['pts'] - career_avg['pts']

                if delta_pts >= 3.0: trend_status = "🚀 上升期 (Career Ascending)"
                elif abs(delta_pts) < 1.0: trend_status = "📈 巔峰期穩定 (Stable Peak Performance)"
                elif delta_pts < -3.0: trend_status = "📉 下滑期 (Performance Decline)"
                else: trend_status = "📊 表現波動 (Fluctuating Performance)"

                report['trend_analysis'] = {
                    'delta_pts': f"{'+' if delta_pts > 0 else ''}{round(delta_pts, 1)}",
                    'trend_status': trend_status,
                }
            else:
                 report['trend_analysis'] = {'trend_status': 'N/A', 'delta_pts': 'N/A'}

            report['season'] = season
        else:
            # ... (N/A 設置邏輯)
            report.update({
                'games_played': 0, 'pts': 'N/A', 'reb': 'N/A', 'ast': 'N/A', 'stl': 'N/A', 'blk': 'N/A', 'tov': 'N/A', 'ato_ratio': 'N/A', 'fg_pct': 'N/A', 'ft_pct': 'N/A', 'fta_per_game': 'N/A', 'min_per_game': 'N/A', 'season': f"無 {season} 賽季數據",
            })
            report['trend_analysis'] = {'trend_status': 'N/A', 'delta_pts': 'N/A'}

        # --- 整合 Reddit 數據 ---
        report['reddit_hot_index'] = reddit_info['hot_index']
        report['reddit_top_tags'] = reddit_info['top_tags']
        
        # ... (獎項列表邏輯保持不變)
        if not awards_df.empty:
            award_pairs = awards_df[['DESCRIPTION', 'SEASON']].apply(lambda x: f"{x['DESCRIPTION']} ({x['SEASON'][:4]})", axis=1).tolist()
            report['awards'] = award_pairs
        else:
            report['awards'] = []

        return report

    except Exception as e:
        # vvvvvv 【最終修正：API 失敗時返回安全字典】 vvvvvv
        return {
            'error': f"數據處理失敗，詳細錯誤: {e}",
            'team_abbr': 'ERR', 'team_full': 'API Error', 'precise_positions': 'N/A', 'games_played': 0, 
            'pts': 'N/A', 'reb': 'N/A', 'ast': 'N/A', 'stl': 'N/A', 'blk': 'N/A', 'tov': 'N/A', 'ato_ratio': 'N/A', 
            'fg_pct': 'N/A', 'ft_pct': 'N/A', 'fta_per_game': 'N/A', 'min_per_game': 'N/A', 
            'trend_analysis': {'trend_status': 'N/A', 'delta_pts': 'N/A', 'delta_reb': 'N/A', 'delta_ast': 'N/A'},
            'reddit_hot_index': 'N/A', 'reddit_top_tags': 'N/A', 'awards': [], 'season': season
        }
        # ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^


# ======================================
# IV. 報告格式化與輸出
# ======================================

def format_report_markdown_streamlit(data):
    """將整理後的數據格式化為 Markdown 報告 (Streamlit 直接渲染)"""
    # 這裡的邏輯已經很乾淨，錯誤發生在數據獲取階段

    if data.get('error'):
        # 這裡的 'data' 已經是安全的錯誤字典
        return f"## ❌ 錯誤報告\n\n{data['error']}"

    style_analysis = analyze_style(data, data.get('position', 'N/A'))
    trend = data['trend_analysis']
    
    awards_list_md = '\n'.join([f"* {award}" for award in data['awards'] if award])
    if not awards_list_md:
        awards_list_md = "* 暫無官方 NBA 獎項記錄"

    markdown_text = f"""
## ⚡ {data['name']} ({data['team_abbr']}) 狀態報告 
**當賽季效力球隊:** **{data['team_full']}**

**📅 當賽季出場數 (GP):** **{data['games_played']}**

**🗺️ 可打位置:** **{data['precise_positions']}**

---

**🔥 社群輿情分析 (Reddit r/nba):**
* **熱度指數 (上週):** {data['reddit_hot_index']}
* **主要爭議點/話題:** **{data['reddit_top_tags']}**

---

**📊 {data['season']} 賽季平均數據:**
* 場均上場時間 (MIN): **{data['min_per_game']}**
* 場均得分 (PTS): **{data['pts']}**
* 場均籃板 (REB): **{data['reb']}**
* 場均助攻 (AST): **{data['ast']}**
* 場均抄截 (STL): **{data['stl']}**
* 場均封阻 (BLK): **{data['blk']}**
* 助攻失誤比 (A/TO): **{data['ato_ratio']}**
* 投籃命中率 (FG%): **{data['fg_pct']}%**
* 罰球命中率 (FT%): **{data['ft_pct']}%**
* 場均罰球數 (FTA): **{data['fta_per_game']}**

---

**📈 生涯表現趨勢分析:**
* **趨勢狀態:** {trend['trend_status']}
* **得分差異 (PTS $\Delta$):** {trend['delta_pts']} (vs. 生涯平均)
* **籃板差異 (REB $\Delta$):** {trend['delta_reb']}
* **助攻差異 (AST $\Delta$):** {trend['delta_ast']}

---

**⭐ 球員風格分析 (Rule-Based):**
* **核心風格:** {style_analysis['core_style']}
* **簡化評級:** {style_analysis['simple_rating']}

---

**🏆 曾經得過的官方獎項 (含年份):**
{awards_list_md}
"""
    return markdown_text

# ====================================================================
# V. Streamlit 界面邏輯 (運行部分)
# ====================================================================

# 設定頁面
st.set_page_config(layout="centered")
st.title("🏀 NBA 球員狀態報告自動生成系統")

# 使用 Streamlit 的 sidebar 創建輸入表單
with st.sidebar:
    st.header("參數設置")
    player_name_input = st.text_input("輸入球員全名:", value="James Harden")
    season_input = st.text_input("輸入查詢賽季:", value="2018-19")
    
    # 創建一個按鈕
    if st.button("🔍 生成報告"):
        if player_name_input:
            with st.spinner(f'正在爬取 {player_name_input} 的 {season_input} 數據...'):
                report_data = get_player_report(player_name_input, season_input)
                markdown_output = format_report_markdown_streamlit(report_data)
                
                # 將結果儲存到 session_state
                st.session_state['report'] = markdown_output
                st.session_state['player_name'] = player_name_input
                st.session_state['season_input'] = season_input
        else:
            st.warning("請輸入一個球員姓名。")

# 顯示主要內容
st.header("生成結果")
if 'report' in st.session_state:
    st.markdown(st.session_state['report'])
