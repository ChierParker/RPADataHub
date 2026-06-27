import operator
import shutil
from pathlib import Path

import pandas as pd
import xlwings as xw

from library.logger import logger


def write_df_to_template(
        df_data: pd.DataFrame,
        file_path_template: Path,
        file_path_excel: Path,
        sheet_name: str = None,
        start_addr: str = "A2",
):
    """
    将 pandas DataFrame 的数据写入到指定的 Excel 模板文件中的特定工作表。

    Args:
        df_data (pd.DataFrame): 要写入 Excel 的数据。
        file_path_template (Path): Excel 模板文件的路径。
        file_path_excel (Path): 输出 Excel 文件的路径。如果文件已存在，则会被覆盖。
        sheet_name (str, optional): 要写入数据的工作表名称。如果未指定，则默认为第一个工作表。
        start_addr (str, optional): 数据开始写入的单元格地址，默认为 'A2'。

    注意:
        - 该函数依赖于 `xlwings` 库来操作 Excel 文件。
        - 需要实现 `read_range` 和 `write_range` 函数，用于读取模板列名和写入数据。
    """
    # 确保输出文件的父目录存在
    file_path_excel.parent.mkdir(parents=True, exist_ok=True)

    # 复制模板文件到输出文件位置
    shutil.copy(file_path_template, file_path_excel)

    # 使用 xlwings 打开输出文件
    app = xw.App(visible=False)
    wb = app.books.open(file_path_excel)
    sht = wb.sheets[0] if sheet_name is None else wb.sheets[sheet_name]

    # 假设 read_range 函数可以读取 Excel 范围并返回一个包含列名的 DataFrame
    df_template = read_range(sht)  # 需要实现这个函数

    # 检查 df_data 和 df_template 的列名、列顺序是否一致
    check_result = operator.eq(df_template.columns.to_list(), df_data.columns.tolist())

    if not check_result:
        # 找出共有的列
        common_columns = [col for col in df_template.columns if col in df_data.columns]

        # 检查是否有模板中存在而 df_data 中缺失的列
        missing_columns = [
            col for col in df_template.columns if col not in df_data.columns
        ]

        # 如果有缺失的列，向 df_data 中添加这些列，使用 NaN 填充
        for col in missing_columns:
            df_data[col] = pd.NA

        # 调整 df_data 的列顺序以匹配模板
        df_data = df_data[common_columns + missing_columns]

    # 假设 write_range 函数可以将 DataFrame 数据写入指定的 Excel 范围
    write_range(df_data, sht, start_addr)  # 需要实现这个函数

    # 关闭 Excel 应用，保存更改
    wb.save()
    wb.close()
    app.quit()


def read_range_from_excel(file_path: Path, sheet_name: str = None, start_addr: str = "A1",
                          using_xlwings: bool = True) -> pd.DataFrame:
    """从 excel 文件中读取指定范围的数据。

    Args:
        file_path (Path): 文件路径。
        sheet_name (str, optional): 工作表名称，默认为 None。
        start_addr (str, optional): 范围的起始地址，默认为 "A1"。
        using_xlwings (bool, optional): 是否使用 xlwings 读取数据，默认为 True。

    Returns:
        pd.DataFrame: 读取的数据。
    """
    if using_xlwings:
        is_opened = False

        # 尝试连接到已经打开的 Excel 应用实例
        if xw.apps.active:
            app = xw.apps.active
        else:
            app = xw.App(visible=False)
            is_opened = True

        # 尝试打开工作簿，如果工作簿已经打开，则直接引用
        try:
            wb = app.books[file_path.name]
        except KeyError:
            # 如果工作簿没有打开，则打开它
            wb = app.books.open(file_path)

        sht = wb.sheets[0] if sheet_name is None else wb.sheets[sheet_name]
        rng = sht.range(start_addr).options(pd.DataFrame, expand='table', index=False).value

        # 检查读取的数据是否为 DataFrame
        if isinstance(rng, pd.DataFrame):
            df = rng
        else:
            # 如果读取的数据不是 DataFrame，则尝试转换
            df = pd.DataFrame(rng)

        logger.info(f"从文件《{file_path.name}》的表<{sht.name}>读取到 {df.shape[0]} 行数据")

        # 只有是当前打开的工作簿，才关闭工作簿
        if is_opened:
            wb.close()
            # 如果没有其他打开的工作簿，则关闭 Excel 应用
            if app.books.count == 0:
                app.quit()

        return df

    else:
        # 使用 pandas 读取 Excel 文件
        return pd.read_excel(file_path, sheet_name=sheet_name, index_col=None)


def write_range_to_excel(df: pd.DataFrame, file_path: Path, sheet_name: str = None, start_addr: str = "A2"):
    """将 DataFrame 写入到 Excel 文件中的指定工作表

    Args:
        df (pd.DataFrame): 要写入的数据
        file_path (Path): 文件路径
        sheet_name (str, optional): 工作表名称，默认为 None
        start_addr (str, optional): 范围的起始地址，默认为 "A1"
    """
    is_opened = False

    # 尝试连接到已经打开的Excel应用实例
    if xw.apps.active:
        app = xw.apps.active
    else:
        app = xw.App(visible=False)
        is_opened = True

    # 尝试打开工作簿，如果工作簿已经打开，则直接引用
    try:
        wb = app.books[file_path.name]
    except KeyError:
        # 如果工作簿没有打开，则打开它
        wb = app.books.open(file_path)

    sht = wb.sheets[0] if sheet_name is None else wb.sheets[sheet_name]

    # 这里假设 write_range 是一个自定义函数，负责将DataFrame写入到Excel的指定范围
    # 请确保你有相应的实现，或者使用类似 sht.range(start_addr).value = df.values 的方式来写入数据
    write_range(df, sht, start_addr)

    wb.save()
    logger.info(f"填写了 {df.shape[0]} 行数据到《{file_path.name}》的表 <{sht.name}> ")

    # 只有是当前打开的工作簿，才关闭工作簿
    if is_opened:
        wb.close()

        # 如果没有其他打开的工作簿，则关闭Excel应用
        if app.books.count == 0:
            app.quit()


def read_range(sht: xw.Sheet, start_addr: str = "A1") -> pd.DataFrame:
    """
    读取 Excel 数据表，返回 DataFrame
    """

    df = sht.range(start_addr).options(pd.DataFrame, index=False, expand="table").value

    return df


def write_range(df: pd.DataFrame, sht: xw.Sheet, start_addr: str = "A2"):
    """
    将 DataFrame 写入到 Excel 数据表
    注意: 保持原格式
    """
    # # 注意: 当只有一行的时候，要注意不能覆盖行号
    # sht.range(start_addr).value = df.values.tolist()
    # 将 DataFrame 数据写入指定的 Excel 工作表范围
    sht.range(start_addr).options(index=False, header=False).value = df.values


def check_template(
        df: pd.DataFrame,
        file_path_template: Path,
        sheet_name: str = None,
        check_order: bool = False,
) -> bool:
    """
    检查 DataFrame 的列名是否与模板文件中指定工作表的列名一致。

    参数:
        df (pd.DataFrame): 需要检查列名的DataFrame。
        file_path_template (Path): 模板文件的路径。
        sheet_name (str, 可选): 工作表名称。如果不填写，则默认为第一个工作表。默认为 None。
        check_order (bool, 可选): 是否检查列名的顺序。默认为 False。

    返回:
        bool: 如果列名（和顺序，如果check_order=True）与模板一致，则返回True，否则返回False。
    """
    # 创建一个不可见的Excel应用实例
    app = xw.App(visible=False)
    wb_template = None
    try:
        # 使用不可见的应用实例来打开工作簿
        wb_template = app.books.open(file_path_template, read_only=True)
        if sheet_name is None:
            sht_template = wb_template.sheets[0]  # 选择第一个工作表
        else:
            sht_template = wb_template.sheets[sheet_name]
        df_template = (
            sht_template.range("A1")
            .expand()
            .options(pd.DataFrame, header=1, index=False)
            .value
        )
        template_columns = df_template.columns.tolist()

    finally:
        # 确保无论如何都关闭工作簿，并退出Excel应用实例
        wb_template.close()
        app.quit()

    # 检查列名是否一致
    check_result = check_columns(df, template_columns, check_order)
    return check_result


def check_columns(
        df: pd.DataFrame, columns_list: list, check_order: bool = False
) -> bool:
    """
    检查 DataFrame 的列名是否与指定的列名列表一致。

    参数:
        df (pd.DataFrame): 需要检查列名的DataFrame。
        columns_list (list): 指定的列名列表。
        check_order (bool, 可选): 是否检查列名的顺序。默认为 False。

    返回:
        bool: 如果列名（和顺序，如果check_order=True）与指定的列名列表一致，则返回True，否则返回False。
    """
    if check_order:
        return operator.eq(columns_list, df.columns.tolist())
    else:
        return set(columns_list) == set(df.columns.tolist())


def write_df_to_json(df: pd.DataFrame, file_path: Path):
    """
    将 DataFrame 写入到 JSON 列表文件。

    :param df: DataFrame
    :type df: pd.DataFrame
    :param file_path: JSON 文件的路径
    :type file_path: Path
    """
    Path(file_path.parent).mkdir(parents=True, exist_ok=True)
    # 使用 orient="records" 来表示DataFrame的每一行作为一个记录，整个DataFrame作为一个列表
    # 去掉 lines=True，以确保整个DataFrame被写为一个JSON数组
    df.to_json(file_path, force_ascii=False, orient="records", indent=4)
    # logger.info(f"写入了 {df.shape[0]} 行数据到文件<{file_path.name}>")


def read_json_to_df(file_path: Path) -> pd.DataFrame:
    """
    从 JSON 文件中读取数据，并将其加载到 DataFrame 中。

    :param file_path: JSON 文件的路径
    :type file_path: Path
    :return: 包含数据的 DataFrame
    :rtype: pd.DataFrame
    """
    # 不使用 lines=True 参数，因为假定JSON文件是一个标准的JSON数组
    df_result = pd.read_json(file_path, orient="records")
    logger.info(f"从文件<{file_path.name}>读取到 {df_result.shape[0]} 行数据")
    return df_result


def align_columns(df_current: pd.DataFrame,
                  file_path_template: Path, sheet_name: str) -> pd.DataFrame:
    """对齐列，确保 df_current 和 file_path_template 中的列名、列顺序一致

    Args:
        df_current (pd.DataFrame): 当前数据
        file_path_template (Path): 模板文件路径
        sheet_name (str): 模板文件中的表单名称

    Returns:
        pd.DataFrame: 对齐后的数据
    """
    # 1) 读取模板文件中的列
    df_template = read_range_from_excel(file_path_template, sheet_name=sheet_name, using_xlwings=False)
    logger.info(f"和模板《{file_path_template.name}》的表 <{sheet_name}> 保持一致")
    # 2) 如果数据列不存在，初始化数据列
    columns_to_add = [column for column in df_template.columns if column not in df_current.columns]
    for column in columns_to_add:
        df_current[column] = None

    # 3) 调整列的顺序
    df_current = df_current[df_template.columns]

    return df_current
