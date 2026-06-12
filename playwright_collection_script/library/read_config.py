import os
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from library.logger import logger
from library.utils import get_app_name, get_path

load_dotenv()


def get_app_data_dir() -> Path:
    """
    获取应用的数据目录

    注意:
    1) 应用数据存档在: 用户目录下的 Documents/Robots/<app_name> 目录下,
    例如 D:/Users/liaohai1/Documents/Robots/<app_name>;
    """

    app_data_dir = Path.home() / "Documents" / "Robots" / "track-news-keywords"
    app_data_dir.mkdir(parents=True, exist_ok=True)

    return app_data_dir


def get_file_path_config() -> Path:
    """
    获取主配置文件路径

    路径逻辑简化：
    - DEBUG_MODE=True: 使用项目data目录下的01_流程配置
    - DEBUG_MODE=False: 使用用户数据目录下的01_流程配置

    :return: 配置文件路径
    """

    file_name_config = f"application-monitor.xlsx"

    # 调试模式下，使用项目data目录
    if os.getenv("DEBUG_MODE") == "True":
        # 计算项目根目录
        main_file_path = Path(__file__).parent.parent / "main.py"
        if main_file_path.exists():
            project_root_dir = main_file_path.parent
            file_path_config = (
                project_root_dir / "data" / "01_流程配置" / file_name_config
            )
        else:
            raise FileNotFoundError("main.py 文件不存在, 请检查路径是否正确。")

        # 确保目录存在
        file_path_config.parent.mkdir(parents=True, exist_ok=True)

        # 如果调试配置文件不存在，从config模板复制
        if not file_path_config.exists():
            config_template = Path(__file__).parent.parent / "config" / file_name_config
            if config_template.exists():
                shutil.copy(config_template, file_path_config)
                logger.info(f"从模板复制配置文件到调试环境: {file_path_config}")
            else:
                err_msg = f"调试模式配置文件不存在且无模板可复制: {file_path_config}"
                logger.error(err_msg)
                raise FileNotFoundError(err_msg)

        logger.info(f"调试模式，配置文件路径: {file_path_config}")
        return file_path_config

    else:
        # 生产模式下，使用用户数据目录
        file_path_config_prd = get_app_data_dir() / "01_流程配置" / file_name_config

        if not file_path_config_prd.exists():
            # 生产配置文件不存在，从config模板复制
            config_template = Path(__file__).parent.parent / "config" / file_name_config
            if config_template.exists():
                file_path_config_prd.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(config_template, file_path_config_prd)
                logger.info(f"从模板复制配置文件到生产环境: {file_path_config_prd}")
            else:
                err_msg = (
                    f"生产模式配置文件不存在且无模板可复制: {file_path_config_prd}"
                )
                logger.error(err_msg)
                raise FileNotFoundError(err_msg)

        logger.info(f"生产模式，配置文件路径: {file_path_config_prd}")
        return file_path_config_prd


def read_config_xlsx(file_path_config: str, sheet_name: str = "01_流程配置") -> dict:
    """
    从 excel 文件中读取配置信息
    :param file_path_config:
    :param sheet_name:
    :return:
    """
    logger.info(f"读取配置文件: {file_path_config}，表: {sheet_name}")

    # 使用 pandas 读取 excel 文件
    df = pd.read_excel(file_path_config, sheet_name=sheet_name)

    # 确保列名为 "配置_名称" 和 "配置_值"
    if not {"配置_名称", "配置_值"}.issubset(df.columns):
        err_msg = f"在配置文件:{file_path_config}，表 <sheet_name> 中没有找到数据列 [配置_名称] 或 [配置_值]，请检查文件格式是否正确"
        logger.error(err_msg)
        raise ValueError(err_msg)

    # 初始化一个空字典来保存结果
    dic_config = {}

    # 遍历每一行
    for index, row in df.iterrows():
        key = row["配置_名称"]
        value = row["配置_值"]

        # 如果 key 不是字符串或以 "配置选项_" 开头，跳过这一行
        if not isinstance(key, str) or key.startswith("配置选项_"):
            continue

        # 如果 value 是 NaN，将其替换为 ""
        if pd.isnull(value):
            value = ""

        # 检查 key 是否重复
        if key in dic_config:
            raise ValueError(f"配置表里存在重复的键值: {key}，请检查并改正")

        # 将 key-value 添加到字典中
        dic_config[key] = value

    return dic_config


def init_file_and_folder(dict_config):
    """
    初始化所有文件夹路径

    简化的路径计算逻辑：
    - DEBUG_MODE=True 时：所有文件和文件夹基于项目data目录计算
    - DEBUG_MODE=False 时：所有文件和文件夹基于用户数据目录计算

    - 遍历 dict_config, 找到[目录结构] Key 下包含"文件、文件夹" 的子 key
    - 如果对应的 value 是相对路径
    - 则补全为绝对路径，join 到基础目录下面
    - 如果是文件夹,且不存在则创建文件夹
    - 如果是文件,且父级目录不存在，则创建父级目录
    :param dict_config:
    :return: dict_config
    """

    logger.info("开始:init_file_and_folder, 初始化所有文件夹路径")

    FOLDER_PREFIX = "文件夹_"
    FILE_PREFIX = "文件_"

    # 1) 计算基础目录路径
    is_debug_mode = os.getenv("DEBUG_MODE") == "True"

    if is_debug_mode:
        # 调试模式：使用项目data目录作为基础目录
        main_file_path = Path(__file__).parent.parent / "main.py"
        if main_file_path.exists():
            project_root_dir = main_file_path.parent
            base_dir = project_root_dir / "data"  # 项目data目录
        else:
            raise FileNotFoundError("main.py 文件不存在, 请检查路径是否正确。")
        logger.info(f"调试模式，使用项目数据目录: {base_dir}")
    else:
        # 生产模式：使用用户数据目录
        base_dir = get_app_data_dir()
        logger.info(f"生产模式，使用用户数据目录: {base_dir}")

    # 2) 递归处理，每个文件、文件夹，如果是相对路径，则补全为绝对路径
    def _process_file_and_folder(dict_obj):

        for key, value in dict_obj.items():
            if isinstance(value, dict):
                _process_file_and_folder(value)

            # 符合前缀，并且非空
            elif (
                key.startswith(FOLDER_PREFIX) or key.startswith(FILE_PREFIX)
            ) and value:

                # 统一使用基础目录
                path = Path(base_dir) / value

                # 更新配置字典中的值为新的绝对路径
                dict_obj[key] = str(path)

                # 如果是文件夹,且不存在则创建文件夹
                if key.startswith(FOLDER_PREFIX):
                    path.mkdir(parents=True, exist_ok=True)

                # 如果是文件, 且父级目录不存在，则创建父级目录
                if key.startswith(FILE_PREFIX):
                    path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("结束:init_file_and_folder")
    _process_file_and_folder(dict_config)

    return dict_config


def init_all_settings(
    file_path_config: Path = None,
    sheet_name: str = "01_流程配置",
    create_temp_folder: bool = True,
) -> dict:
    """
    读取配置文件，补全所有文件夹路径，创建文件夹
    :return: 配置字典
    """
    logger.info("开始:init_all_settings, 读取配置文件，补全所有文件夹路径，创建文件夹")
    load_dotenv()

    if file_path_config is None:
        file_path_config = get_file_path_config()

    # 1 读取excel配置文件
    dict_config = read_config_xlsx(file_path_config, sheet_name)

    # 2 计算"数据目录"，补全所有文件夹路径，并创建文件夹
    dict_config = init_file_and_folder(dict_config)

    # 3 添加[运行时间]、[运行日期]（系统时间, 将其格式化为 "yyyy-mm-dd_HHmmss" 格式)
    formatted_now = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    dict_config["运行时间"] = formatted_now
    dict_config["运行日期"] = datetime.now().strftime("%Y-%m-%d")

    # 4 修改临时文件夹, 添加运行时间
    path = Path(dict_config["文件夹_临时文件"]) / get_app_name() / formatted_now
    dict_config["文件夹_临时文件"] = path
    if create_temp_folder:
        path.mkdir(parents=True, exist_ok=True)
        logger.info(
            f"当前运行时间是: {formatted_now}, 临时文件夹是: {dict_config['文件夹_临时文件']}"
        )

    logger.info("结束:init_all_settings")
    return dict_config


def get_config_value(config_dict, key, default=0):
    """尝试从配置字典中获取一个值并转换为整数，如果不存在或转换失败，则返回默认值。"""
    try:
        # 尝试获取并转换值
        return int(config_dict.get(key, default))
    except ValueError:
        # 如果转换失败，返回默认值
        return default


def get_dict_config(create_temp_folder: bool = True) -> dict:
    return init_all_settings(
        file_path_config=get_file_path_config(),
        sheet_name="01_流程配置",
        create_temp_folder=create_temp_folder,
    )


def get_application_list() -> list:
    """
    获取应用程序列表。

    Returns:
        list: 应用程序列表。

    """
    df_applications = pd.read_excel(get_file_path_config(), sheet_name="02_应用列表")
    df_applications_enabled = df_applications[df_applications["是否启用"] == "是"]
    logger.info(
        f"应用程序列表上启用了: {len(df_applications_enabled)} / {len(df_applications)} 个应用"
    )
    return df_applications_enabled.to_dict(orient="records")


def get_app_config(app_name=get_app_name()) -> dict:
    """
    从应用程序列表获取应用程序配置
    """
    logger.info(f"获取应用程序配置: {app_name}")
    df_applications = pd.read_excel(get_file_path_config(), sheet_name="02_应用列表")
    df_app = df_applications[df_applications["应用名称"] == app_name]
    if len(df_app) == 0:
        err_msg = f"没有找到应用程序配置: {app_name}"
        logger.error(err_msg)
        raise ValueError(err_msg)
    return df_app.to_dict(orient="records")[0]


if __name__ == "__main__":
    # logger.info(get_file_path_config())
    # logger.info(get_dict_config(create_temp_folder=False))
    logger.info(get_application_list())
