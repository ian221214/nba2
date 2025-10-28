# -*- coding: utf-8 -*-
# NBA Player Report Streamlit App - Final and Stable Version (BBR Advanced Scraping)

import pandas as pd
import streamlit as st
import requests # <-- 傳統爬蟲庫
from bs4 import BeautifulSoup # <-- 傳統爬蟲庫
import time # <-- 爬蟲倫理延遲

from nba_api.stats.static import players
from nba_api.stats.endpoints import (
    playerawards, 
    commonplayerinfo, 
    playercareerstats, 
)

# 設置 BBR 爬蟲參數
BBR_BASE_URL = "https://www.basketball-reference.com"
BBR_DELAY = 4  # <-- BBR 要求較高的延遲時間 (4秒)

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
    """將 NBA API 返回的通用位置（Guard, F-C 等）轉換為所有精確位置（PG, SG, SF, PF, C）。"""
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
        return {'core_style': '數據不足', 'simple_rating': '請嘗試查詢有數據的賽季。'}

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
# II. 傳統爬蟲函數 (Basketball-Reference)
# ======================================

def get_bbr_player_slug(player_name):
    """將 NBA 名稱轉換為 BBR 格式的 Slug (例如 Jayson Tatum -> tatumja01)。"""
    # 這是爬取 BBR 的關鍵步驟，但由於無法在單一函數中完全自動化，這裡使用一個簡化/模擬的 slug
    # 警告：此函數是簡化版本，可能對一些特殊名稱（如 Jrue Holiday）無效
    name_parts = player_name.lower().split()
    if len(name_parts) >= 2:
        return f"{name_parts[-1][:5]}{name_parts[0][:2]}01"
    else:
        return None

@st.cache_data(ttl=3600 * 6) # 緩存 6 小時，避免頻繁請求 BBR
def get_bbr_advanced_data(player_name, season):
    """執行 BBR 爬蟲，獲取進階數據，例如 PER。"""
    
    player_slug = get_bbr_player_slug(player_name)
    if not player_slug:
        return {'PER': 'N/A', 'VORP': 'N/A', 'ScrapeStatus': '無法生成 Slug'}
        
    # 格式化賽季年份 (BBR 用結束年份，例如 2023-24 -> 2024)
    end_year = str(int(season.split('-')[-1]))
    
    # BBR 進階數據頁面的 URL (使用進階數據總頁面)
    url = f"{BBR_BASE_URL}/players/{player_slug[0]}/{player_slug}.html"

    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    time.sleep(BBR_DELAY) # 遵守爬蟲倫理：設置延遲

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return {'PER': 'N/A', 'VORP': 'N/A', 'ScrapeStatus': f"爬蟲失敗 (Code: {response.status_code})"}

        soup = BeautifulSoup(response.content, 'html.parser')
        
        # BBR 將進階數據表隱藏在 HTML 註釋中，需要特殊處理
        # 尋找註釋中的 'advanced' 表格
        advanced_table_html = None
        for comment in soup.find_all(string=lambda t: isinstance(t, str) and 'advanced' in t):
            advanced_table_html = str(comment).replace('', '')
            break
        
        if advanced_table_html:
            # 使用 pandas 讀取 HTML 表格
            df_list = pd.read_html(advanced_table_html)
            advanced_df = df_list[0] if df_list else None
        else:
            # 如果沒有找到註釋中的表格
            advanced_df = None

        if advanced_df is not None and 'PER' in advanced_df.columns:
            # 篩選出目標賽季的數據
            season_row = advanced_df[advanced_df['Season'] == season]
            
            if not season_row.empty:
                # 提取 PER 和 VORP
                per = season_row['PER'].iloc[0]
                vorp = season_row['VORP'].iloc[0]
                
                return {
                    'PER': round(float(per), 1) if pd.notna(per) else 'N/A',
                    'VORP': round(float(vorp), 1) if pd.notna(vorp) else 'N/A',
                    'ScrapeStatus': '成功'
                }
        
        return {'PER': 'N/A', 'VORP': 'N/A', 'ScrapeStatus': '未找到 Advanced 表格'}

    except Exception as e:
        return {'PER': 'N/A', 'VORP': 'N/A', 'ScrapeStatus': f"爬蟲發生錯誤: {type(e).__name__}"}

# ======================================
# III. 主數據獲取函數 (整合爬蟲)
# ======================================

def get_player_report(player_name, season='2023-24'):
    """獲取並整理特定球員的狀態報告數據。"""
    player_id = get_player_id(player_name)
    
    # 獲取 BBR 進階數據 (傳統爬蟲)
    bbr_info = get_bbr_advanced_data(player_name, season) 

    if not player_id:
        return {
            'error': f"找不到球員：{player_name}。請檢查姓名是否正確。",
            'name': player_name, 'team_abbr': 'N/A', 'team_full': 'N/A', 'precise_positions': 'N/A', 
            'games_played': 0, 'pts': 'N/A', 'reb': 'N/A', 'ast': 'N/A', 'stl': 'N/A', 'blk': 'N/A', 'tov': 'N/A', 'ato_ratio': 'N/A', 
            'fg_pct': 'N/A', 'ft_pct': 'N/A', 'fta_per_game': 'N/A', 'min_per_game': 'N/A', 
            'trend_analysis': {'trend_status': 'N/A', 'delta_pts': 'N/A', 'delta_reb': 'N/A', 'delta_ast': 'N/A'},
            'awards': [], 'contract_year': 'N/A', 'salary': 'N/A', 'season': season,
            'bbr_per': bbr_info['PER'],
            'bbr_vorp': bbr_info['VORP'],
            'bbr_status': bbr_info['ScrapeStatus'],
        }

    try:
        # 1. 獲取官方統計數據 (NBA API)
        info = commonplayerinfo.CommonPlayerInfo(player_id=player_id)
        info_df = info.get_data_frames()[0]
        stats = playercareerstats.PlayerCareerStats(player_id=player_id)
        stats_data = stats.get_data_frames()[0]
        career_totals_df = stats.get_data_frames()[1] 
        season_stats = stats_data[stats_data['SEASON_ID'] == season]
        awards = playerawards.Awards(player_id=player_id)
        awards_df = awards.get_data_frames()[0]
        
        report = {}
        # ... (基本資訊與球隊邏輯保持不變)
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
                career_avg = {}
                total_gp_career = career_totals_df.loc[0, 'GP']
                
                # 計算生涯平均
                career_avg['pts'] = round(career_totals_df.loc[0, 'PTS'] / total_gp_career, 1)
                career_avg['reb'] = round(career_totals_df.loc[0, 'REB'] / total_gp_career, 1)
                career_avg['ast'] = round(career_totals_df.loc[0, 'AST'] / total_gp_career, 1)
                
                # 1. 計算 Delta
                delta_pts = report['pts'] - career_avg['pts']
                delta_reb = report['reb'] - career_avg['reb']
                delta_ast = report['ast'] - career_avg['ast']

                # 2. 判斷趨勢狀態
                if delta_pts >= 3.0: trend_status = "🚀 上升期 (Career Ascending)"
                elif abs(delta_pts) < 1.0: trend_status = "📈 巔峰期穩定 (Stable Peak Performance)"
                elif delta_pts < -3.0: trend_status = "📉 下滑期 (Performance Decline)"
                else: trend_status = "📊 表現波動 (Fluctuating Performance)"

                report['trend_analysis'] = {
                    'delta_pts': f"{'+' if delta_pts > 0 else ''}{round(delta_pts, 1)}",
                    'delta_reb': f"{'+' if delta_reb > 0 else ''}{round(delta_reb, 1)}",
                    'delta_ast': f"{'+' if delta_ast > 0 else ''}{round(delta_ast, 1)}",
                    'trend_status': trend_status,
                }
            else:
                 report['trend_analysis'] = {'trend_status': '無法計算生涯趨勢', 'delta_pts': 'N/A', 'delta_reb': 'N/A', 'delta_ast': 'N/A'}

            # 薪資資訊 (佔位符)
            report['contract_year'] = '數據源無法獲取'
            report['salary'] = '數據源無法獲取'
            report['season'] = season
        else:
            # 無數據時的 N/A 設置
            report.update({
                'games_played': 0, 'pts': 'N/A', 'reb': 'N/A', 'ast': 'N/A', 'stl': 'N/A', 'blk': 'N/A', 'tov': 'N/A', 'ato_ratio': 'N/A',
                'fg_pct': 'N/A', 'ft_pct': 'N/A', 'fta_per_game': 'N/A', 'min_per_game': 'N/A', 'contract_year': 'N/A', 'salary': 'N/A', 'season': f"無 {season} 賽季數據",
            })
            report['trend_analysis'] = {'trend_status': 'N/A', 'delta_pts': 'N/A', 'delta_reb': 'N/A', 'delta_ast': 'N/A'}

        # --- 整合 BBR 數據 ---
        report['bbr_per'] = bbr_info['PER']
        report['bbr_vorp'] = bbr_info['VORP']
        report['bbr_status'] = bbr_info['ScrapeStatus']
        
        # ... (獎項列表邏輯保持不變)
        if not awards_df.empty:
            award_pairs = awards_df[['DESCRIPTION', 'SEASON']].apply(lambda x: f"{x['DESCRIPTION']} ({x['SEASON'][:4]})", axis=1).tolist()
            report['awards'] = award_pairs
        else:
            report['awards'] = []

        return report

    except Exception as e:
        return {
            'error': f"數據處理失敗，詳細錯誤: {e}",
            'name': player_name, 'team_abbr': 'ERR', 'team_full': 'API Error', 'precise_positions': 'N/A', 
            'games_played': 0, 'pts': 'N/A', 'reb': 'N/A', 'ast': 'N/A', 'stl': 'N/A', 'blk': 'N/A', 'tov': 'N/A', 'ato_ratio': 'N/A', 
            'fg_pct': 'N/A', 'ft_pct': 'N/A', 'fta_per_game': 'N/A', 'min_per_game': 'N/A',
            'trend_analysis': {'trend_status': 'N/A', 'delta_pts': 'N/A', 'delta_reb': 'N/A', 'delta_ast': 'N/A'},
            'awards': [], 'contract_year': 'N/A', 'salary': 'N/A', 'season': season,
            'bbr_per': 'N/A',
            'bbr_vorp': 'N/A',
            'bbr_status': 'NBA API 失敗導致跳過 BBR 爬蟲',
        }

# ======================================
# IV. 報告格式化與輸出
# ======================================

def format_report_markdown_streamlit(data):
    """將整理後的數據格式化為 Markdown 報告 (Streamlit 直接渲染)"""
    if data.get('error'):
        return f"## ❌ 錯誤報告\n\n{data['error']}"

    style_analysis = analyze_style(data, data.get('position', 'N/A'))
    trend = data['trend_analysis']
    
    awards_list_md = '\n'.join([f"* {award}" for award in data['awards'] if award])
    if not awards_list_md:
        awards_list_md = "* 暫無官方 NBA 獎項記錄"

    # 設置 BBR 狀態提示
    bbr_status_text = ""
    if data['bbr_per'] != 'N/A' and data['bbr_status'] == '成功':
        bbr_per_text = f"* 球員效率值 (PER): **{data['bbr_per']}**"
        bbr_vorp_text = f"* VORP 值: **{data['bbr_vorp']}**"
    else:
        bbr_per_text = f"* 球員效率值 (PER): **無法獲取**"
        bbr_vorp_text = f"* VORP 值: **無法獲取**"
        bbr_status_text = f"\n  * **傳統爬蟲狀態：** {data['bbr_status']}"

    markdown_text = f"""
## ⚡ {data['name']} ({data['team_abbr']}) 狀態報告 
**當賽季效力球隊:** **{data['team_full']}**

**📅 當賽季出場數 (GP):** **{data['games_played']}**

**🗺️ 可打位置:** **{data['precise_positions']}**

---

**📊 {data['season']} 賽季平均數據:**
{bbr_per_text}
{bbr_vorp_text}
{bbr_status_text}
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
    player_name_input = st.text_input("輸入球員全名:", value="Jayson Tatum")
    season_input = st.text_input("輸入查詢賽季:", value="2023-24")
    
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
