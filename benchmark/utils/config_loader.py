# 工具模块：读取配置文件

# 例如：
# load_yaml("config/sla.yaml")

# 返回：
# dict

import yaml

def load_yaml(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def validate_configs(sla_config, workload_config):
    errors = []

    for key in ("ttft_p99", "tpot_p90"):
        if key not in sla_config:
            errors.append(f"Missing SLA config: {key}")
        elif float(sla_config[key]) <= 0:
            errors.append(f"SLA config must be positive: {key}")

    schedule_mode = workload_config.get("schedule_mode", "classic")
    if schedule_mode not in ("classic", "realistic"):
        errors.append("schedule_mode must be 'classic' or 'realistic'")

    inference_type = workload_config.get("inference_type", "fake")
    if inference_type not in ("fake", "vllm", "ollama"):
        errors.append("inference_type must be 'fake', 'vllm', or 'ollama'")

    max_users = int(workload_config.get("max_users", 1))
    if max_users <= 0:
        errors.append("max_users must be positive")

    pressure = workload_config.get("pressure", {})
    if pressure:
        min_rps = float(pressure.get("min_rps", 0.0))
        max_rps = float(pressure.get("max_rps", 0.0))
        rps_precision = float(pressure.get("rps_precision", 0.0))
        if min_rps <= 0 or max_rps <= 0:
            errors.append("pressure.min_rps and pressure.max_rps must be positive")
        if min_rps >= max_rps:
            errors.append("pressure.min_rps must be smaller than pressure.max_rps")
        if rps_precision <= 0:
            errors.append("pressure.rps_precision must be positive")

    if errors:
        raise ValueError("Invalid configuration:\n- " + "\n- ".join(errors))
