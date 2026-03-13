# 工具模块：读取配置文件

# 例如：
# load_yaml("config/sla.yaml")

# 返回：
# dict

import yaml

def load_yaml(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)