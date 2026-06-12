import re
from pathlib import Path

import pandas as pd

from library.logger import logger
from library.storage import (read_range_from_excel)


def split_string_to_list(string_text: str) -> list:
    """将字符串分隔的字符串转换为列表

    注意: 分割符号可以是 "、" "," " "。,，# 中的任意一个

    Args:
        string_text (str): 输入字符串

    Returns:
        list: 字符串列表
    """
    # 使用正则表达式定义分隔符：逗号、顿号、空格、句号、中文逗号、井号
    separators = r"[、, 。,，# ]+"
    # 使用 re.split() 根据分隔符分割字符串
    word_list = re.split(separators, string_text)

    # 如果拆分出空白的分段，则清除

    # 清除前后空白
    return [word.strip() for word in word_list if word.strip()]


def list_to_string(word_list: list) -> str:
    """将列表转换为字符串

    Args:
        word_list (list): 字符串列表

    Returns:
        str: 字符串
    """
    text = ""
    if len(word_list) > 0:
        text = "、".join(word_list)
    return text


def remove_words(str_content: str, remove_words: list) -> str:
    """
    删除文本中指定的单词列表中的所有单词。

    参数:
    - str_content (str): 原始文本字符串。
    - remove_words (list): 需要从文本中删除的单词列表。

    返回:
    - str: 删除指定单词后的文本字符串。

    示例:
     remove_words("这是一个测试文本", ["一个", "测试"])
    '这是 文本'
    """
    for word in remove_words:
        str_content = str_content.replace(word, "")
    return str_content.strip()


def check_final_result(df_check_keywords_result: pd.DataFrame) -> pd.DataFrame:
    """
    检查最终结果，如果匹配了关键词，但是也匹配了排除关键词，则将是否匹配改为否

    （筛选关键词有值） and （叠加关键词有值 or 未配置）and (排除关键词无值 or 未配置)
    """

    rewrite_rows_count: int = 0
    for idx, row in df_check_keywords_result.iterrows():
        str_level_1 = remove_words(str(row["筛选关键词"]), ["未设置", "未匹配", "None"])
        str_level_2 = remove_words(str(row["叠加关键词"]), ["未设置", "未匹配", "None"])
        str_level_3 = remove_words(str(row["排除关键词"]), ["未设置", "未匹配", "None"])

        # 默认是 "否"
        df_check_keywords_result.loc[idx, "是否匹配"] = "否"

        # 逐级判断
        if str_level_1:
            if str_level_2:
                # 一级关键词命中，二级关键词命中，是
                df_check_keywords_result.loc[idx, "是否匹配"] = "是"
                rewrite_rows_count += 1

                if str_level_3:
                    # 一级关键词命中，二级关键词命中，三级关键词命中，否
                    df_check_keywords_result.loc[idx, "是否匹配"] = "否"
                    rewrite_rows_count -= 1

            else:
                # 一级命中，但是二级为空再判断是未匹配还是未配置
                if "未设置" in row["叠加关键词"]:
                    df_check_keywords_result.loc[idx, "是否匹配"] = "是"
                    rewrite_rows_count += 1

                    # 只要三级关键词命中，则不匹配
                    if str_level_3:
                        df_check_keywords_result.loc[idx, "是否匹配"] = "否"
                        rewrite_rows_count -= 1
        else:
            df_check_keywords_result.loc[idx, "是否匹配"] = "否"

        # logger.warning(f"{str_level_1},{str_level_2},{str_level_3},{df_check_keywords_result.loc[idx, '是否匹配']}")

    # logger.info(f"排除了 {rewrite_rows_count} 行记录")
    return df_check_keywords_result


def get_keywords(file_path_keywords: Path) -> pd.DataFrame:
    """读取关键词配置文件

    Args:
        file_path_keywords (Path): 配置文件路径

    Returns:
        pd.DataFrame: 包含关键词和分组的DataFrame
    """
    # 1) 读取数据
    df_keywords = read_range_from_excel(file_path_keywords, sheet_name="关键词列表", using_xlwings=False)

    # 2) 筛选 "是否启用" = "是" 的记录
    origin_group_count = df_keywords.shape[0]
    df_keywords = df_keywords[df_keywords["是否启用"] == "是"]
    logger.info(f"筛选后有 {df_keywords.shape[0]}/{origin_group_count} 组关键词")

    # 3) 所有数据列转换为字符串，None 转换为 ""
    df_keywords = df_keywords.fillna("").astype(str)

    return df_keywords


def check_keywords(df_keywords: pd.DataFrame, news_id: str, news_content: str, row_dict: dict,
                   append_not_match_row: bool = True) -> pd.DataFrame:
    """检查文本中是否包含关键词
    注意，只有筛选关键词匹配成功，才会继续匹配叠加关键词和排除关键词
    Args:
        df_keywords (pd.DataFrame): 包含关键词和分组的 DataFrame
        news_id (str): 新闻编号
        news_content (str): 新闻内容
        row_dict (dict): 新闻内容的字典，需要补全其它字段
        append_not_match_row (bool): 如果未匹配，则是否追加一行数据到结果中
    Returns:
        pd.DataFrame: 包含匹配关键词的 DataFrame
    """

    # 1) 初始化结果 DataFrame,columns 是 df_keywords 和 row_dict 的并集
    columns = list(set(df_keywords.columns) | set(row_dict.keys()))
    df_check_keywords_result = pd.DataFrame(columns=columns)

    # 2) 遍历关键词列表，添加数据行
    check_keywords_result_rows = []
    for idx, row in df_keywords.iterrows():

        # 1) 先按照一级关键词进行匹配(字段名:筛选关键词)
        keywords_level_1 = split_string_to_list(row["筛选关键词"])
        result_level_1 = []
        result_level_2 = []
        result_level_3 = []
        for keyword in keywords_level_1:
            # 如果是英文，则不区分大小写
            if keyword.isascii():
                keyword = keyword.lower()
                news_content = news_content.lower()

            if keyword in news_content:
                result_level_1.append(keyword)

        # 2) 如果一级关键词匹配成功，则继续匹配二级关键词(字段名:叠加关键词)、三级关键词(字段名:排除关键词)
        # 注意: [叠加关键词] 和 [排除关键词] 可能为空
        if len(result_level_1) > 0:
            # 2.1) 匹配二级关键词
            keywords_level_2 = split_string_to_list(row["叠加关键词"])
            if len(keywords_level_2) == 0:
                match_result = "未设置"
                result_level_2.append(match_result)
            for keyword in keywords_level_2:
                # 如果是英文，则不区分大小写
                if keyword.isascii():
                    keyword = keyword.lower()
                    news_content = news_content.lower()

                if keyword in news_content:
                    result_level_2.append(keyword)
            if len(result_level_2) == 0:
                match_result = "未匹配"
                result_level_2.append(match_result)

            # 2.2) 匹配三级关键词
            keywords_level_3 = split_string_to_list(row["排除关键词"])
            if len(keywords_level_3) == 0:
                match_result = "未设置"
                result_level_3.append(match_result)

            for keyword in keywords_level_3:
                # 如果是英文，则不区分大小写
                if keyword.isascii():
                    keyword = keyword.lower()
                    news_content = news_content.lower()

                if keyword in news_content:
                    result_level_3.append(keyword)

            if len(result_level_3) == 0:
                match_result = "未匹配"
                result_level_3.append(match_result)

        # # 输出提示信息
        # if len(result_level_1) > 0:
        #     logger.info(f"新闻编号: {news_id}, 匹配了关键词: {result_level_1}")

        # 4) 如果匹配，则将匹配结果写入到 df_check_keywords_result 中
        if len(result_level_1) > 0:
            # 4.1) 记录当前字段
            result_row = {
                "新闻编号": news_id,
                "关键词编号": row["关键词编号"],
                "关键词分组": row["关键词分组"],
                "筛选关键词": list_to_string(result_level_1),
                "叠加关键词": list_to_string(result_level_2),
                "排除关键词": list_to_string(result_level_3),
                "是否匹配": "是"
            }

            # 4.2) 找到其它字段，补全到结果中
            columns_other = set(row_dict.keys()) - set(result_row.keys())
            for key in columns_other:
                result_row[key] = row_dict[key]

            # 4.3) 添加到结果列表
            check_keywords_result_rows.append(result_row)

    # 5) 将匹配结果写入到 df_check_keywords_result 中
    if len(check_keywords_result_rows) > 0:
        df_check_keywords_result = pd.DataFrame(check_keywords_result_rows)
        logger.trace(f"新闻编号: {news_id}, 匹配了 {len(check_keywords_result_rows)} 组关键词")
    else:
        # 5.1)如果追加原数据行，则新增一行数据，追加到结果中
        logger.trace(f"新闻编号: {news_id}, 未匹配任何关键词")
        if append_not_match_row:
            columns = list(set(df_keywords.columns) | set(row_dict.keys()))
            # 每个字段用空格填充
            result_row = {key: None for key in columns}
            # 补全新闻字段
            for key, value in row_dict.items():
                result_row[key] = value

            result_row["是否匹配"] = "否"

            # 追加一行数据到 df_check_keywords_result 中
            df_check_keywords_result = pd.concat([df_check_keywords_result, pd.DataFrame([result_row])],
                                                 ignore_index=True)

    # 6) 基于排除规则，方法判断最终是否匹配
    df_check_keywords_result = check_final_result(df_check_keywords_result)

    # logger.trace(f"新闻编号: {news_id}, 返回了 {len(df_check_keywords_result)} 行数据")
    return df_check_keywords_result


if __name__ == "__main__":
    df_keywords = get_keywords(
        Path(r"D:\Users\liaohai1\Documents\Robots\track-news-keywords\01_流程配置\关键词列表.xlsx"))

    row_dict = {
        "新闻标题": "测试新闻标题",
        "新闻内容": "【强降雨持续 南昌铁路局动态调整三条铁路部分旅客列车开行方案】根据气象部门预报，未来三天，江西北部等部分地区有大到暴雨，江西西北部等地部分地区有大暴雨和特大暴雨，局地有雷暴大风等强对流天气。为确保铁路运输安全，南昌铁路局计划对管内衢九铁路、武九铁路、铜九铁路部分旅客列车采取临时停运安全措施。旅客朋友在收到列车停运短信，或在12306查询到列车停运信息后，可自车票发站乘车日期起的30日内（含当日），在12306网站（12306手机App）或火车站人工窗口办理全额退票手续，因列车停运导致退票不收取退票费。铁路部门温馨提示，将根据降雨、风速等情况，动态调整列车运行方案，广大旅客可关注站车广播公告，或通过铁路12306平台及时掌握最新列车运行资讯，合理安排行程。*（央视新闻）",
        "发布时间": "2021-07-01 00:01:00",
        "发布日期": "2021-07-01"
    }

    df_check_keywords_result = check_keywords(df_keywords, "202107010001",
                                              news_content=row_dict["新闻内容"], row_dict=
                                              row_dict)
    from library.utils import get_path

    df_check_keywords_result.to_csv(get_path("test/data/check_result.csv"), index=False)
