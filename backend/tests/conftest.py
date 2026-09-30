"""测试环境的模型配置隔离。

必须在任何 app.* 模块导入前生效：模型配置读取会触发 .env 加载（override=True），
若不先声明跳过，测试就会拿到真实凭据并把请求指向真实端点。
"""

from __future__ import annotations

import os

from app.core.model_config import skip_env_file

os.environ["DEEPSEEK_API_KEY"] = "test-key"
os.environ["DEEPSEEK_ENDPOINT"] = "https://example.invalid/v1"
os.environ["DEEPSEEK_MODEL"] = "test-main-model"
os.environ["QWEN_CODER_MODEL"] = "test-coder-model"
os.environ["QWEN_MATH_MODEL"] = "test-math-model"
os.environ["QWEN3_VL_PLUS_MODEL"] = "test-vision-model"

skip_env_file()
