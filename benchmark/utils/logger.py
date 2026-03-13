# 工具模块：日志系统

# 记录：
# 系统状态
# SLA变化
# 加压过程

# 示例：
# [INFO] concurrency=120
# [WARNING] TTFT approaching SLA
# [ERROR] SLA violated

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)