from openpyxl import load_workbook
from pathlib import Path
import pandas as pd
import json
from library.utils import get_app_data_dir, get_app_data_file
from library.logger import logger

po_account_config_path = get_app_data_file('config', 'po-accountConfig.xlsx')

def get_account():
    file_path = get_app_data_file('config', 'accountConfig.xlsx')
    logger.info('当前配置文件为：' + file_path)
    account_dic = {}
    df = pd.read_excel(file_path)
    for index, item in df.iterrows():
        # if item[0] not in account_dic:
        #     account_dic.update({item[0]: []})
        account_dic[item[0]]= [item[1], item[2], item[3], item[4]]
    return account_dic



def get_keyword_JSON(in_country):
    if in_country == 'GB':
        in_country = 'UK'
    file_path = get_app_data_file('config', 'winrobot-data-config.json')
    logger.info('当前配置文件为：' + file_path)
    with open(file_path, 'r', encoding='utf-8') as file:
        json_data = json.load(file)  # 解析为Python字典/列表
    json_list = []
    for k,v in json_data.items():
        json_list = json_list + v
    df = pd.DataFrame(json_list)
    df_filter = df[df['country_code'] == in_country]
    df_sorted = df_filter.sort_values('rank')
    df_keyword = df_sorted.reset_index(drop=True)
    return df_keyword


def get_recollect_keyword_JSON(in_country):
    # if in_country == 'GB':
    #     in_country = 'UK'
    file_path = get_app_data_file('config', 'winrobot-data-config-recollect.json')
    logger.info('当前配置文件为：' + file_path)
    with open(file_path, 'r', encoding='utf-8') as file:
        json_data = json.load(file)  # 解析为Python字典/列表
    json_list = []
    for k,v in json_data.items():
        json_list = json_list + v
    df = pd.DataFrame(json_list)
    try:
        df = df.rename(columns={'TERM': 'keyword'})
    except:
        logger.info('没有TREM列, 不做处理')
    df_filter = df[df['country_code'] == in_country]
    df_sorted = df_filter.sort_values('rank')
    df_keyword = df_sorted.reset_index(drop=True)
    return df_keyword

def get_account_shops_list():
    """
    读取指定的 Excel 文件，筛选 'AccountDetail' sheet 页中 '是否启用' 为 '是' 的行，
    并返回对应的 '店铺' 名称列表。

    :return: 包含启用的 '店铺' 名称的列表
    """
    logger.info('当前配置文件为：' + po_account_config_path)

    try:
        # 使用 pandas 读取 Excel 文件
        df = pd.read_excel(po_account_config_path, sheet_name='AccountDetail')

        # 检查是否包含所需的列
        if '是否启用' not in df.columns or '店铺' not in df.columns:
            raise ValueError("表头中未找到 '是否启用' 或 '店铺' 字段")

        # 筛选 '是否启用' 为 '是' 的行，并获取对应的 '店铺' 名称
        enabled_shops = df.loc[df['是否启用'] == '是', '店铺'].tolist()

        return enabled_shops

    except Exception as e:
        print(f"发生错误: {e}")
        return []


# def get_process_config_list():
    """
    读取 Excel 文件的第二列内容并保存到列表中。
    
    :param file_path: Excel 文件路径
    :return: 第二列内容的列表
    """
    logger.info('当前配置文件为：' + po_account_config_path)

    try:

        # 使用 pandas 读取 Excel 文件
        df = pd.read_excel(po_account_config_path, sheet_name='DataDetail')

        # 获取第二行的所有列
        second_row = df.iloc[0, :].tolist()  # 获取第二行（索引从 0 开始）
        process_config_list = second_row

        return process_config_list

    except Exception as e:
        print(f"发生错误: {e}")
        return []


def get_country_profiles():
    """
    读取国家与Profile的对应关系
    """

    try:
        df = pd.read_excel(po_account_config_path, sheet_name='Winrobot-login-config')
        country_profiles = {}
        for _, row in df.iterrows():
            country = row['国家']
            profile = row['Profile']
            amz_url = row['亚马逊地址']
            country_profiles[country] = {
                'profile': profile,
                'amz_url': amz_url
            }
        return country_profiles
    except Exception as e:
        print(f"读取国家Profile配置时发生错误: {e}")
        return {}


def get_country_shops():
    """
    获取每个国家对应的店铺列表
    """
    try:
        df = pd.read_excel(po_account_config_path, sheet_name='AccountDetail')
        country_shops = {}
        for _, row in df.iterrows():
            if row['是否启用'] == '是':
                country = row['国家']
                shop = row['店铺']
                if country not in country_shops:
                    country_shops[country] = []
                country_shops[country].append(shop)
        return country_shops
    except Exception as e:
        print(f"读取国家店铺配置时发生错误: {e}")
        return {}


if __name__ == "__main__":
    a = get_keyword_JSON("IT")
    print(a)

